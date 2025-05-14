# backend/app/routes/twilio_webhook.py

from datetime import datetime, timezone as dt_timezone # Keep existing import for timezone
import logging
import traceback
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Request, status, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
import pytz
from typing import Optional, Dict, Any # Added Dict, Any for type hinting

from app.database import get_db
from app.models import (
    BusinessProfile,
    Engagement,
    Message, # Ensure Message model is imported
    Conversation as ConversationModel,
    ConsentLog,
    Customer,
    MessageTypeEnum, # Assuming MessageTypeEnum is in app.models
    MessageStatusEnum # Assuming MessageStatusEnum is in app.models
)

from app.services.ai_service import AIService
from app.services.consent_service import ConsentService
from app.config import settings
from app.services.twilio_service import TwilioService

from app.schemas import normalize_phone_number as normalize_phone
import re

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/inbound", response_class=PlainTextResponse)
async def receive_sms(
    request: Request,
    db: Session = Depends(get_db)
) -> PlainTextResponse:
    message_sid_from_twilio = "N/A"
    from_number_raw = "N/A"
    to_number_raw = "N/A"
    form_data = {}

    # Instantiate services
    twilio_service = TwilioService(db=db)
    ai_service = AIService(db=db)
    consent_service = ConsentService(db=db)

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
        body_lower = body_raw.lower()
        message_sid_from_twilio = form_data.get("MessageSid", "N/A")

        log_prefix = f"INBOUND_SMS [SID:{message_sid_from_twilio}]"
        logger.info(f"{log_prefix}: From={from_number}(raw:{from_number_raw}), To={to_number}(raw:{to_number_raw}), Body='{body_raw}'")

        if not all([from_number, to_number, body_raw]):
            logger.error(f"{log_prefix}: Missing Twilio params. Form: {dict(form_data)}")
            return PlainTextResponse("Missing params", status_code=status.HTTP_200_OK)

        # --- Consent Processing ---
        consent_log_response = await consent_service.process_sms_response(
            phone_number=from_number, response=body_lower
        )
        if consent_log_response:
            logger.info(f"{log_prefix}: Consent response handled for {from_number}.")
            return consent_log_response
        logger.info(f"{log_prefix}: Message from {from_number} not direct consent update. Proceeding.")

        # --- Business and Customer Lookup ---
        business = db.query(BusinessProfile).filter(BusinessProfile.twilio_number == to_number).first()
        if not business:
            logger.error(f"{log_prefix}: No business for Twilio number {to_number}.")
            return PlainTextResponse("Receiving number not associated", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Routed to Business ID {business.id} ({business.business_name}).")

        customer = db.query(Customer).filter(
            Customer.phone == from_number, Customer.business_id == business.id
        ).first()

        now_utc_aware = datetime.now(pytz.UTC) # Use a consistent UTC timestamp

        initial_consent_created_this_request = False
        if not customer:
            logger.info(f"{log_prefix}: New customer from {from_number}. Creating.")
            customer = Customer(
                phone=from_number,
                business_id=business.id,
                customer_name=f"Inbound Lead ({from_number})", # More generic name
                opted_in=False, # Default for new customer; will be updated by consent flow
                created_at=now_utc_aware,
                lifecycle_stage="Lead", 
                pain_points="Unknown", 
                interaction_history=f"First contact via SMS: {body_raw[:100]}"
            )
            db.add(customer)
            try:
                db.flush() # Get customer.id for ConsentLog
            except Exception as e_flush_cust:
                db.rollback()
                logger.error(f"{log_prefix}: DB error flushing new customer {from_number}: {e_flush_cust}", exc_info=True)
                return PlainTextResponse("Server error creating customer profile.", status_code=status.HTTP_200_OK)

            initial_consent = ConsentLog(
                customer_id=customer.id,
                phone_number=from_number,
                business_id=business.id,
                method="customer_initiated_sms", 
                status="pending", 
                sent_at=now_utc_aware,
            )
            db.add(initial_consent)
            initial_consent_created_this_request = True
            logger.info(f"{log_prefix}: Created new Customer ID {customer.id} and initial 'pending' ConsentLog ID {initial_consent.id if hasattr(initial_consent, 'id') else 'Pending'}.")
        else:
            logger.info(f"{log_prefix}: Matched Customer ID {customer.id} ({customer.customer_name}). Current opted_in flag from DB: {customer.opted_in}")

        latest_consent_log_for_check = db.query(ConsentLog).filter(
            ConsentLog.customer_id == customer.id,
        ).order_by(desc(ConsentLog.created_at)).first()

        if latest_consent_log_for_check and latest_consent_log_for_check.status == "opted_out":
            logger.warning(f"{log_prefix}: Customer {customer.id} ({from_number}) is OPTED_OUT based on ConsentLog. Discarding message.")
            if initial_consent_created_this_request: 
                db.rollback() 
            return PlainTextResponse("Customer has opted out.", status_code=status.HTTP_200_OK)

        logger.info(f"{log_prefix}: Customer {customer.id} not explicitly opted-out by log. Latest ConsentLog status: '{latest_consent_log_for_check.status if latest_consent_log_for_check else 'None'}'.")

        # --- Conversation Handling ---
        conversation = db.query(ConversationModel).filter(
            ConversationModel.customer_id == customer.id,
            ConversationModel.business_id == business.id, 
            ConversationModel.status == 'active'
        ).first()

        if not conversation:
            conversation = ConversationModel(
                id=uuid.uuid4(), customer_id=customer.id, business_id=business.id,
                started_at=now_utc_aware, last_message_at=now_utc_aware, status='active'
            )
            db.add(conversation)
            try:
                db.flush()
            except Exception as e_flush_conv:
                db.rollback()
                logger.error(f"{log_prefix}: DB error flushing new conversation for customer {customer.id}: {e_flush_conv}", exc_info=True)
                return PlainTextResponse("Server error initializing conversation.", status_code=status.HTTP_200_OK)
            logger.info(f"{log_prefix}: New Conversation ID {conversation.id} for Customer {customer.id}.")
        else:
            conversation.last_message_at = now_utc_aware
            logger.info(f"{log_prefix}: Existing Conversation ID {conversation.id}. Updated last_message_at.")

        # --- Log Inbound Message ---
        # Engagement record will be created AFTER AI processing
        inbound_message_record = Message(
            conversation_id=conversation.id, business_id=business.id, customer_id=customer.id,
            content=body_raw, message_type='inbound', status='received',
            sent_at=now_utc_aware, 
            message_metadata={'twilio_sid': message_sid_from_twilio, 'source': 'customer_reply'}
        )
        db.add(inbound_message_record)
        try:
            db.flush() # Get ID for inbound_message_record
        except Exception as e_flush_in_msg:
            db.rollback()
            logger.error(f"{log_prefix}: DB error flushing inbound message for customer {customer.id}: {e_flush_in_msg}", exc_info=True)
            return PlainTextResponse("Server error saving message.", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Customer message logged. MsgID: {inbound_message_record.id}.")


        # --- AI Response Generation & Handling (MODIFIED SECTION) ---
        ai_response_data: Optional[Dict[str, Any]] = None
        engagement_status_after_ai = "pending_review" # Default status for engagement
        ai_response_for_engagement_field: Optional[str] = None # For Engagement.ai_response field

        try:
            ai_response_data = await ai_service.generate_sms_response(
                message=body_raw, business_id=business.id, customer_id=customer.id
            )
        except Exception as ai_err:
            logger.error(f"{log_prefix}: AI response generation failed for business {business.id}, customer {customer.id}: {ai_err}", exc_info=True)
            # ai_response_data remains None, engagement will be 'pending_review'

        # Determine if AI will auto-reply as FAQ
        # The key "ai_should_reply_directly_as_faq" comes from your updated AIService
        should_ai_reply_directly_as_faq = (
            ai_response_data and
            business.enable_ai_faq_auto_reply and # Business setting
            ai_response_data.get("ai_should_reply_directly_as_faq", False) # AI service's decision
        )

        if should_ai_reply_directly_as_faq:
            logger.info(f"{log_prefix}: Business {business.id} has enable_ai_faq_auto_reply=True and AI indicates direct FAQ reply. Attempting AI auto-reply.")
            
            ai_reply_text_for_sending = ai_response_data.get("text", "")
            if not ai_reply_text_for_sending: # Should not happen if ai_should_reply_directly_as_faq is True
                logger.error(f"{log_prefix}: AI indicated direct reply but no text found. Skipping auto-reply.")
                engagement_status_after_ai = "pending_review"
            else:
                message_content_to_send = ai_reply_text_for_sending
                appended_opt_in_prompt_to_autopilot = False

                is_customer_pending_opt_in = not customer.opted_in and (
                    not latest_consent_log_for_check or latest_consent_log_for_check.status == "pending"
                )
                if is_customer_pending_opt_in:
                    message_content_to_send += "\n\nWant to stay in the loop? Reply YES to stay in touch. ❤️ Msg&Data rates may apply. Reply STOP to cancel."
                    appended_opt_in_prompt_to_autopilot = True
                    logger.info(f"{log_prefix}: Appended opt-in prompt to AI autopilot reply for pending customer {customer.id}.")

                try:
                    sent_message_sid = await twilio_service.send_sms(
                        to=customer.phone,
                        message_body=message_content_to_send,
                        business=business,
                        customer=customer, 
                        is_direct_reply=True 
                    )

                    if sent_message_sid:
                        engagement_status_after_ai = "auto_replied_faq" 
                        logger.info(f"{log_prefix}: AI auto-reply sent. SID: {sent_message_sid}. Status: {engagement_status_after_ai}.")
                        
                        # Log this AI auto-reply as an outbound Message
                        outbound_ai_message_content_structured = {
                            "text": ai_reply_text_for_sending, # Original AI text before opt-in append
                            "is_faq_answer": True, # Since it's an FAQ autopilot reply
                            "source": "faq_autopilot", # Or another specific source from ai_response_data if available
                            "appended_opt_in_prompt": appended_opt_in_prompt_to_autopilot
                        }
                        outbound_message = Message(
                            conversation_id=conversation.id, business_id=business.id, customer_id=customer.id,
                            content=json.dumps(outbound_ai_message_content_structured),
                            message_type=MessageTypeEnum.OUTBOUND_AI_REPLY, # Specific type
                            status=MessageStatusEnum.SENT, # Mark as sent
                            sent_at=datetime.now(pytz.UTC), 
                            message_metadata={
                                'twilio_sid': sent_message_sid,
                                'source': 'faq_autopilot', 
                                'original_customer_message_sid': message_sid_from_twilio
                            }
                        )
                        db.add(outbound_message)
                        logger.info(f"{log_prefix}: Logged AI auto-reply as Message.")
                        # ai_response_for_engagement_field will remain None as this is not a "draft"
                    else: 
                        logger.error(f"{log_prefix}: twilio_service.send_sms returned no SID for AI auto-reply.")
                        engagement_status_after_ai = "pending_review" 
                except Exception as send_exc:
                    logger.error(f"{log_prefix}: Unexpected error sending AI auto-reply: {send_exc}", exc_info=True)
                    engagement_status_after_ai = "pending_review" 
        
        # If AI did not auto-reply, prepare its response for the Engagement record (as a draft suggestion)
        if engagement_status_after_ai == "pending_review" and ai_response_data and ai_response_data.get("text"):
            # Store the structured response from AIService if available and not auto-replied
            ai_response_for_engagement_field = json.dumps({
                "text": ai_response_data.get("text"),
                "is_faq_answer": ai_response_data.get("is_faq_answer", False), # Reflect what AI service determined
            })
            logger.info(f"{log_prefix}: AI response prepared for engagement draft: '{ai_response_data.get('text', '')[:50]}...'")
        elif engagement_status_after_ai == "pending_review":
             logger.info(f"{log_prefix}: No AI response available or not suitable for draft, engagement pending review.")


        # --- Create Engagement Record ---
        # This record is always created to track the interaction.
        # Its status and ai_response field will indicate what happened.
        engagement = Engagement(
            customer_id=customer.id, business_id=business.id, message_id=inbound_message_record.id,
            response=body_raw, # This is the customer's message
            ai_response=ai_response_for_engagement_field, # AI's suggestion (if not auto-replied) or None
            status=engagement_status_after_ai, # Reflects if auto-reply happened or pending
            created_at=now_utc_aware,
            # sent_at for engagement is when AI auto-replied, or null if manual/pending
            sent_at=datetime.now(pytz.UTC) if engagement_status_after_ai == "auto_replied_faq" else None
        )
        db.add(engagement)
        try:
            db.flush() # Get engagement.id
            logger.info(f"{log_prefix}: Engagement record created. EngID: {engagement.id}, Status: {engagement.status}")
        except Exception as e_flush_eng:
            db.rollback()
            logger.error(f"{log_prefix}: DB error flushing engagement for customer {customer.id}: {e_flush_eng}", exc_info=True)
            return PlainTextResponse("Server error creating engagement record.", status_code=status.HTTP_200_OK)


        # --- Owner Notification Logic ---
        # Notify owner if AI did NOT auto-reply (engagement status is 'pending_review')
        # AND business owner wants notifications.
        should_notify_owner_now = (
            business.notify_owner_on_reply_with_link and
            business.business_phone_number and
            business.slug and
            engagement.status == "pending_review" # CRITICAL: Only notify if AI didn't handle it
        )

        if should_notify_owner_now:
            logger.info(f"{log_prefix}: Preparing owner notification for EngID {engagement.id} (status is 'pending_review').")
            try:
                deep_link_url = f"{settings.FRONTEND_APP_URL}/inbox/{business.slug}?activeCustomer={customer.id}&engagementId={engagement.id}"
                ai_draft_preview_for_notification = ""
                if engagement.ai_response: # Check if there's an AI response to preview
                    try:
                        ai_data_for_preview = json.loads(engagement.ai_response)
                        ai_text_for_preview = ai_data_for_preview.get("text", "")
                        if not isinstance(ai_text_for_preview, str): 
                            ai_text_for_preview = str(ai_text_for_preview)
                        ai_draft_preview_for_notification = f"\nAI Draft: \"{ai_text_for_preview[:40]}{'...' if len(ai_text_for_preview) > 40 else ''}\""
                    except Exception as preview_err:
                        logger.warning(f"{log_prefix}: Could not parse ai_response JSON for notification preview: {preview_err}")

                notification_sms_body = (
                    f"AI Nudge: New SMS from {customer.customer_name} ({customer.phone}).\n"
                    f"Message: \"{body_raw[:70]}{'...' if len(body_raw) > 70 else ''}\""
                    f"{ai_draft_preview_for_notification}\n"
                    f"View & Reply: {deep_link_url}"
                )
                await twilio_service.send_sms(
                    to=business.business_phone_number,
                    message_body=notification_sms_body, 
                    business=business, 
                    is_direct_reply=False 
                )
                logger.info(f"{log_prefix}: Owner SMS notification sent via TwilioService to {business.business_phone_number}.")
            except Exception as notify_err:
                logger.error(f"{log_prefix}: Failed to send owner notification SMS (via TwilioService): {notify_err}", exc_info=True)
        elif engagement.status != "pending_review":
            logger.info(f"{log_prefix}: Owner notification skipped because engagement status is '{engagement.status}'.")
        else: 
            logger.info(
                f"{log_prefix}: Owner notification conditions not met. "
                f"Notify: {business.notify_owner_on_reply_with_link}, "
                f"OwnerPhone: {'Set' if business.business_phone_number else 'Not Set'}, "
                f"Slug: {'Set' if business.slug else 'Not Set'}, "
                f"EngStatus: {engagement.status}"
            )

        # --- Final Commit ---
        try:
            db.commit()
            logger.info(f"{log_prefix}: Database changes committed successfully.")
        except Exception as db_commit_err:
            db.rollback()
            logger.error(f"{log_prefix}: Final DB commit failed: {db_commit_err}", exc_info=True)
            return PlainTextResponse("Error saving interaction details.", status_code=status.HTTP_200_OK)

        return PlainTextResponse("SMS Received", status_code=status.HTTP_200_OK)

    except HTTPException as http_exc:
        logger.error(f"HTTPException in webhook: {http_exc.detail} (Status: {http_exc.status_code})", exc_info=True)
        if db.is_active: 
            db.rollback()
        return PlainTextResponse(f"Handled error: {http_exc.detail}", status_code=status.HTTP_200_OK)
    except Exception as e:
        current_form_data_str = str(dict(form_data))[:500] 
        logger.error(f"UNHANDLED EXCEPTION in webhook processing. SID: {message_sid_from_twilio}, From: {from_number_raw}, To: {to_number_raw}, Form Data (partial): {current_form_data_str}. Error: {e}", exc_info=True)
        if db.is_active:
            db.rollback()
        return PlainTextResponse("Internal Server Error processing webhook", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        logger.info(f"=== Twilio Webhook: END /inbound processing for SID:{message_sid_from_twilio} ===")