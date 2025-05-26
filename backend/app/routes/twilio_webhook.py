# backend/app/routes/twilio_webhook.py

from datetime import datetime, timezone as dt_timezone
import logging
import traceback
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Request, status, Response, BackgroundTasks
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
import pytz
from typing import Optional, Dict, Any

from app.database import get_db
from app.models import (
    BusinessProfile,
    Engagement,
    Message,
    Conversation as ConversationModel,
    ConsentLog,
    Customer,
    MessageTypeEnum,
    MessageStatusEnum,
    SenderTypeEnum,
    AppointmentRequest, # Ensured import
    AppointmentRequestStatusEnum, # Ensured import for checking status
    OptInStatus
)

from app.services.ai_service import AIService # General AI
from app.services.consent_service import ConsentService
from app.config import get_settings
settings = get_settings()
from app.services.twilio_service import TwilioService
from app.services.appointment_service import AppointmentService
from app.services.appointment_ai_service import AppointmentAIService # For parsing intent if needed directly here (though service uses it)


from app.schemas import normalize_phone_number as normalize_phone
import re

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/inbound", response_class=PlainTextResponse)
async def receive_sms(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> PlainTextResponse:
    message_sid_from_twilio = "N/A"
    from_number_raw = "N/A"
    to_number_raw = "N/A"
    form_data = {}

    twilio_service = TwilioService(db=db)
    # ai_service = AIService(db=db) # Instantiated later if needed
    consent_service = ConsentService(db=db)
    appointment_service = AppointmentService(db=db)

    try:
        form_data = await request.form()
        from_number_raw = form_data.get("From", "")
        to_number_raw = form_data.get("To", "")

        try:
            from_number = normalize_phone(from_number_raw)
        except ValueError as e:
            logger.error(f"INBOUND_SMS [SID_UNKNOWN]: Invalid 'From' phone: '{from_number_raw}'. Err: {e}")
            return PlainTextResponse(f"Invalid 'From' number: {from_number_raw}", status_code=status.HTTP_200_OK)
        try:
            to_number = normalize_phone(to_number_raw)
        except ValueError as e:
            logger.error(f"INBOUND_SMS [SID_UNKNOWN]: Invalid 'To' phone: '{to_number_raw}'. Err: {e}")
            return PlainTextResponse(f"Invalid 'To' number: {to_number_raw}", status_code=status.HTTP_200_OK)

        body_raw = form_data.get("Body", "").strip()
        message_sid_from_twilio = form_data.get("MessageSid", f"NO_SID_FALLBACK_{uuid.uuid4()}")

        log_prefix = f"INBOUND_SMS [SID:{message_sid_from_twilio}]"
        logger.info(f"{log_prefix}: From={from_number}(raw:{from_number_raw}), To={to_number}(raw:{to_number_raw}), Body='{body_raw}'")

        if not all([from_number, to_number, body_raw]):
            logger.warning(f"{log_prefix}: Missing some Twilio params or empty body. Form: {dict(form_data)}. Will proceed if From/To are present.")
            if not all([from_number, to_number]):
                 logger.error(f"{log_prefix}: Critical Twilio params From/To missing. Aborting.")
                 return PlainTextResponse("Missing critical params", status_code=status.HTTP_200_OK)

        # --- MOVED BUSINESS AND CUSTOMER IDENTIFICATION EARLIER ---
        business = db.query(BusinessProfile).filter(BusinessProfile.twilio_number == to_number).first()
        if not business:
            logger.error(f"{log_prefix}: No business profile found for Twilio number {to_number}.")
            return PlainTextResponse("Receiving number not associated with a business.", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Routed to Business ID {business.id} ({business.business_name}).")

        now_utc_aware = datetime.now(dt_timezone.utc) # Use dt_timezone if imported as such, else timezone.utc
        customer = db.query(Customer).filter(
            Customer.phone == from_number, Customer.business_id == business.id
        ).first()
        
        if not customer:
            logger.info(f"{log_prefix}: New customer from {from_number} for Business ID {business.id}. Creating.")
            customer = Customer(
                phone=from_number, business_id=business.id,
                customer_name=f"Inbound Lead ({from_number})", # Consider making name nullable or more generic
                sms_opt_in_status=OptInStatus.PENDING, # Use imported Enum member
                created_at=now_utc_aware, 
                updated_at=now_utc_aware, # Set updated_at on creation too
                lifecycle_stage="Lead", # Example stage
            )
            db.add(customer)
            try:
                db.flush() # Flush to get customer.id for ConsentLog
                initial_consent = ConsentLog(
                    customer_id=customer.id, phone_number=from_number, business_id=business.id,
                    method="customer_initiated_sms", status=OptInStatus.PENDING, # Use Enum member
                    sent_at=now_utc_aware, # Or replied_at since it's an inbound trigger
                    created_at=now_utc_aware,
                    updated_at=now_utc_aware
                )
                db.add(initial_consent)
                logger.info(f"{log_prefix}: Created new Customer ID {customer.id} and initial 'pending' ConsentLog ID {initial_consent.id if initial_consent else 'N/A'}.")
            except Exception as e_flush_cust:
                db.rollback()
                logger.error(f"{log_prefix}: DB error flushing new customer {from_number} or initial consent: {e_flush_cust}", exc_info=True)
                return PlainTextResponse("Server error creating customer profile.", status_code=status.HTTP_200_OK)
        else:
            logger.info(f"{log_prefix}: Matched existing Customer ID {customer.id} ({customer.customer_name}).")
        # --- END MOVED BUSINESS AND CUSTOMER IDENTIFICATION ---

        # Now that 'customer' and 'business' are defined, process consent
        consent_log_response = await consent_service.process_sms_response(
            db_customer=customer,
            business=business,
            sms_body=body_raw,
            message_sid=message_sid_from_twilio,
            twilio_phone_number=to_number, # This is the Twilio number that received the message
            business_phone=business.business_phone_number # Business's primary contact number
        )
        if consent_log_response:
            logger.info(f"{log_prefix}: Consent keywords processed for customer {customer.id}. Twilio response sent by ConsentService.")
            try: 
                db.commit() # Commit changes made by consent_service (customer status, new consent log)
            except Exception as e: 
                db.rollback()
                logger.error(f"{log_prefix} DB Commit Error after consent_service processing: {e}", exc_info=True)
            return consent_log_response # Return the PlainTextResponse from consent_service

        # If consent_log_response is None, it means consent service didn't handle it with a direct reply.
        # Proceed with message logging and other processing.

        # Opt-out check (re-check status after consent_service might have updated it)
        # Refresh customer to get the latest status if consent_service committed and changed it
        # However, if consent_service commits, the current session 'customer' object might be stale.
        # It's better if consent_service doesn't commit but stages changes, and a single commit happens here.
        # For now, assuming consent_service might have updated customer.sms_opt_in_status
        db.refresh(customer) # Get the latest status after consent_service call
        
        if customer.sms_opt_in_status == OptInStatus.OPTED_OUT:
            logger.warning(f"{log_prefix}: Customer {customer.id} is OPTED_OUT. Discarding message processing beyond consent.")
            # Commit any pending changes (like new customer creation or the opt-out consent log)
            try: db.commit()
            except Exception as e: db.rollback(); logger.error(f"{log_prefix} DB Commit Error for opted-out customer: {e}", exc_info=True)
            return PlainTextResponse("Customer has opted out.", status_code=status.HTTP_200_OK) # Or just 204
        
        logger.info(f"{log_prefix}: Customer {customer.id} not opted-out. Current consent status: '{customer.sms_opt_in_status.value}'.")

        conversation = db.query(ConversationModel).filter(
            ConversationModel.customer_id == customer.id,
            ConversationModel.business_id == business.id,
            # ConversationModel.status == 'active' # Consider if filtering by active is always needed
        ).order_by(desc(ConversationModel.last_message_at)).first()

        if not conversation:
            conversation = ConversationModel(
                id=uuid.uuid4(), customer_id=customer.id, business_id=business.id,
                started_at=now_utc_aware, last_message_at=now_utc_aware, status='active'
            )
            db.add(conversation)
            logger.info(f"{log_prefix}: New active Conversation ID {conversation.id} created.")
        else:
            conversation.last_message_at = now_utc_aware
            if conversation.status != 'active': # Reactivate if it was closed, for example
                conversation.status = 'active'
                logger.info(f"{log_prefix}: Reactivated existing Conversation ID {conversation.id}.")
            else:
                logger.info(f"{log_prefix}: Using existing active Conversation ID {conversation.id}. Updated last_message_at.")
        
        try: db.flush() # Get conversation.id if new
        except Exception as e_flush_conv:
            db.rollback(); logger.error(f"{log_prefix}: DB error flushing conversation: {e_flush_conv}", exc_info=True)
            return PlainTextResponse("Server error with conversation.", status_code=status.HTTP_200_OK)

        inbound_message_record = Message(
            conversation_id=conversation.id,
            business_id=business.id,
            customer_id=customer.id,
            content=body_raw,
            message_type=MessageTypeEnum.INBOUND,
            status=MessageStatusEnum.RECEIVED,
            sender_type=SenderTypeEnum.CUSTOMER,  # <-- ADD THIS LINE
            sent_at=now_utc_aware,  # 'sent_at' for inbound might be better named 'received_at' or use 'created_at'
            created_at=now_utc_aware,
            updated_at=now_utc_aware,
            twilio_message_sid=message_sid_from_twilio,
            message_metadata={'source': 'customer_sms_reply'}
        )
        db.add(inbound_message_record)
        try: db.flush() # Get inbound_message_record.id
        except Exception as e_flush_msg:
            db.rollback(); logger.error(f"{log_prefix}: DB error flushing inbound message: {e_flush_msg}", exc_info=True)
            return PlainTextResponse("Server error saving message.", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Inbound message logged. DB ID: {inbound_message_record.id}.")

        # --- APPOINTMENT PROCESSING LOGIC ---
        appointment_processed_this_interaction = False
        processed_appointment_request_obj: Optional[AppointmentRequest] = None 

        try:
            logger.info(f"{log_prefix} Checking for existing business-initiated proposal for Customer ID {customer.id}")
            existing_business_proposal = db.query(AppointmentRequest).filter(
                AppointmentRequest.customer_id == customer.id,
                AppointmentRequest.business_id == business.id,
                AppointmentRequest.status == AppointmentRequestStatusEnum.BUSINESS_INITIATED_PENDING_CUSTOMER_REPLY
            ).order_by(desc(AppointmentRequest.created_at)).first()

            if existing_business_proposal:
                logger.info(f"{log_prefix} Found existing business-initiated proposal (ID: {existing_business_proposal.id}). Handling customer reply.")
                updated_request = await appointment_service.handle_customer_reply_to_proposal(
                    existing_request=existing_business_proposal,
                    sms_body=body_raw,
                    inbound_message_id=inbound_message_record.id,
                    business=business, 
                    customer=customer   
                )
                if updated_request:
                    appointment_processed_this_interaction = True
                    processed_appointment_request_obj = updated_request
                    logger.info(f"{log_prefix} Customer reply to proposal processed. ApptReq ID: {updated_request.id}, New Status: {updated_request.status.value}")
            
            if not appointment_processed_this_interaction:
                logger.info(f"{log_prefix} No active business proposal reply processed. Checking for new customer-initiated appointment intent...")
                newly_created_request = await appointment_service.create_request_from_sms_intent(
        
                    business=business, 
                    customer=customer, 
                    sms_body=body_raw, 
                    inbound_message_id=inbound_message_record.id
                )
                if newly_created_request:
                    appointment_processed_this_interaction = True
                    processed_appointment_request_obj = newly_created_request
                    logger.info(f"{log_prefix} New AppointmentRequest ID: {newly_created_request.id} created from SMS. Status: {newly_created_request.status.value}")
                else:
                    logger.info(f"{log_prefix} SMS was not identified as a new appointment intent by the service.")

        except Exception as e_appt_svc:
            logger.error(f"{log_prefix} EXCEPTION during appointment service processing: {e_appt_svc}", exc_info=True)
        
        # --- GENERAL AI REPLY / ENGAGEMENT DRAFTING ---
        should_send_general_ai_reply = not appointment_processed_this_interaction and business.enable_ai_faq_auto_reply # Check if general AI reply is enabled
        ai_response_for_engagement_field: Optional[str] = None
        engagement_status_after_ai = MessageStatusEnum.PENDING_REVIEW # Default
        
        if should_send_general_ai_reply:
            logger.info(f"{log_prefix} No appointment processed & AI FAQ/auto-reply enabled. Attempting general AI response.")
            ai_service = AIService(db=db) # Ensure AIService is instantiated
            try:
                ai_response_data = await ai_service.generate_sms_response(
                    message=body_raw, business_id=business.id, customer_id=customer.id
                )
                if ai_response_data and ai_response_data.get("text"):
                    ai_text_reply = ai_response_data.get("text")
                    is_faq = ai_response_data.get("is_faq_answer", False)
                    ai_response_for_engagement_field = json.dumps({
                        "text": ai_text_reply,
                        "is_faq_answer": is_faq,
                        "source": "ai_service_general_reply"
                    })
                    logger.info(f"{log_prefix} General AI response draft: '{ai_text_reply[:50]}...'. Is FAQ: {is_faq}")
                    # Potentially auto-send if it's a FAQ and business has that setting
                    # This part needs more logic if you want auto-send for FAQs
                    if is_faq: # Example: if it's an FAQ, maybe it gets auto-approved or sent
                        engagement_status_after_ai = MessageStatusEnum.AUTO_REPLIED_FAQ # Or similar custom status
                        # If you want to auto-send FAQ replies:
                        # background_tasks.add_task(twilio_service.send_sms, to=customer.phone, message_body=ai_text_reply, business=business)
                        # logger.info(f"{log_prefix} Auto-sending FAQ reply based on business setting.")
                else:
                    logger.info(f"{log_prefix} General AI did not provide a text response.")
            except Exception as ai_err:
                logger.error(f"{log_prefix}: General AI response generation failed: {ai_err}", exc_info=True)
        elif appointment_processed_this_interaction:
            logger.info(f"{log_prefix} Appointment interaction processed. Req ID: {processed_appointment_request_obj.id if processed_appointment_request_obj else 'N/A'}.")
            # Check if there's an ai_suggested_reply from the appointment service first
            if processed_appointment_request_obj and processed_appointment_request_obj.ai_suggested_reply:
                 ai_response_for_engagement_field = json.dumps({
                     "text": processed_appointment_request_obj.ai_suggested_reply,
                     "source": "appointment_service_note"
                 })
            # Only create a generic status draft if the status is NOT CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL
            # AND there wasn't a more specific ai_suggested_reply.
            elif processed_appointment_request_obj and \
                 processed_appointment_request_obj.status != AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL:
                 ai_response_for_engagement_field = json.dumps({
                     "text": f"Debug Info: Appt. Status: {processed_appointment_request_obj.status.value}. Req: {processed_appointment_request_obj.parsed_requested_time_text or 'Time TBD'}",
                     "source": "appointment_service_status_other" # Changed source for clarity
                 })
            else:
                 # For CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL, or if no other condition met,
                 # set to None so no AI draft content is added to the engagement for this specific update.
                 # The owner will use the Nudge Card.
                 ai_response_for_engagement_field = None
                 if processed_appointment_request_obj and processed_appointment_request_obj.status == AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL:
                    logger.info(f"{log_prefix} Skipping content for Engagement AI draft as appointment is CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL. Owner will use Nudge Card.")

        engagement = Engagement(
            customer_id=customer.id, business_id=business.id, message_id=inbound_message_record.id,
            response=body_raw, ai_response=ai_response_for_engagement_field,
            status=engagement_status_after_ai, 
            created_at=now_utc_aware, updated_at=now_utc_aware, # Set timestamps
            source="customer_sms_reply_engagement"
        )
        db.add(engagement)
        try: db.flush()
        except Exception as e_flush_eng:
            db.rollback(); logger.error(f"{log_prefix}: DB error flushing engagement: {e_flush_eng}", exc_info=True)
            return PlainTextResponse("Server error creating engagement.", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Engagement ID: {engagement.id} created/updated. Status: {engagement.status.value}")

        # --- OWNER NOTIFICATION LOGIC ---
        if business.notify_owner_on_reply_with_link and business.business_phone_number:
            notification_sms_body = ""
            deep_link_url_segment = ""

            if appointment_processed_this_interaction and processed_appointment_request_obj:
                status_desc = processed_appointment_request_obj.status.name.replace('_', ' ').title()
                time_info = processed_appointment_request_obj.parsed_requested_time_text or \
                            (processed_appointment_request_obj.parsed_requested_datetime_utc.strftime('%a, %b %d @ %I:%M %p') if processed_appointment_request_obj.parsed_requested_datetime_utc else "Time TBD")
                
                notification_sms_body = (
                    f"AI Nudge: Appt Update from {customer.customer_name or customer.phone}. "
                    f"Status: {status_desc}. Time: {time_info}. "
                    f"Msg: \"{body_raw[:30]}{'...' if len(body_raw) > 30 else ''}\"."
                )
                deep_link_url_segment = f"/inbox/{business.slug}?activeCustomer={customer.id}&appointmentRequestId={processed_appointment_request_obj.id}"
            
            elif engagement.status == MessageStatusEnum.PENDING_REVIEW :
                ai_draft_preview = ""
                if engagement.ai_response:
                    try:
                        ai_resp_json = json.loads(engagement.ai_response)
                        ai_text = ai_resp_json.get("text", "")
                        ai_draft_preview = f"\nAI Draft: \"{ai_text[:40]}{'...' if len(ai_text) > 40 else ''}\""
                    except: pass
                
                notification_sms_body = (
                    f"AI Nudge: New SMS from {customer.customer_name or customer.phone}.\n"
                    f"Message: \"{body_raw[:70]}{'...' if len(body_raw) > 70 else ''}\""
                    f"{ai_draft_preview}"
                )
                deep_link_url_segment = f"/inbox/{business.slug}?activeCustomer={customer.id}&engagementId={engagement.id}"
            
            if notification_sms_body and deep_link_url_segment:
                full_deep_link = f"{settings.FRONTEND_APP_URL}{deep_link_url_segment}"
                notification_sms_body += f"\nView: {full_deep_link}"
                
                logger.info(f"{log_prefix}: Queuing owner notification SMS to {business.business_phone_number}")
                background_tasks.add_task(
                    twilio_service.send_sms_to_owner, # Ensure this method exists and handles its own errors
                    business_owner_phone=business.business_phone_number,
                    message_body=notification_sms_body,
                    # business=business # Pass business if send_sms_to_owner needs the Twilio number from it
                )

        try:
            db.commit()
            logger.info(f"{log_prefix}: All database changes committed successfully.")
        except Exception as final_commit_err:
            db.rollback()
            logger.error(f"{log_prefix}: Final DB commit FAILED: {final_commit_err}", exc_info=True)
            # Still return 204 to Twilio if possible, as we've logged the error.
            # Twilio will retry if it doesn't get a 2xx response.
            return Response(status_code=status.HTTP_204_NO_CONTENT)


        logger.info(f"{log_prefix}: Processing complete. Returning 204 to Twilio.")
        return Response(status_code=status.HTTP_204_NO_CONTENT) # Success, no content reply to Twilio

    except HTTPException as http_exc:
        # ... (existing HTTPException handling) ...
        logger.error(f"INBOUND_SMS [SID:{message_sid_from_twilio}] HTTPException: {http_exc.detail} (Status: {http_exc.status_code})", exc_info=False)
        if db.is_active: db.rollback()
        # Return 200 OK to Twilio even for handled errors to prevent retries for bad data, but log it.
        return PlainTextResponse(f"Webhook handled error: {http_exc.detail}", status_code=status.HTTP_200_OK)

    except Exception as e:
        # ... (existing general Exception handling) ...
        current_form_data_str = str(dict(form_data))[:500] # Limit size of form data in log
        error_trace = traceback.format_exc()
        logger.error(f"INBOUND_SMS [SID:{message_sid_from_twilio}] UNHANDLED EXCEPTION. From: {from_number_raw}, To: {to_number_raw}, Form: {current_form_data_str}. Error: {e}\nTRACEBACK:\n{error_trace}")
        if db.is_active: db.rollback()
        # Return 200 OK to Twilio to prevent retries for unhandled server errors, but log it thoroughly.
        return PlainTextResponse("Internal Server Error processing webhook. Error has been logged.", status_code=status.HTTP_200_OK)
    # finally:
        # db.close() # Not needed with Depends(get_db)
        # logger.info(f"=== Twilio Webhook: END /inbound processing for SID:{message_sid_from_twilio} ===")