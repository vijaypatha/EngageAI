# backend/app/routes/twilio_webhook.py

from datetime import datetime, timezone as dt_timezone
import logging
import traceback
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Request, status, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
import pytz
from typing import Optional

from app.database import get_db
from app.models import (
    BusinessProfile,
    Engagement,
    Message,
    Conversation as ConversationModel,
    ConsentLog,
    Customer
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
                # Ensure other required fields for Customer model have defaults or are handled
                lifecycle_stage="Lead", # Example default
                pain_points="Unknown",  # Example default
                interaction_history=f"First contact via SMS: {body_raw[:100]}" # Example default
            )
            db.add(customer)
            try:
                db.flush() # Get customer.id for ConsentLog
            except Exception as e_flush_cust:
                db.rollback()
                logger.error(f"{log_prefix}: DB error flushing new customer {from_number}: {e_flush_cust}", exc_info=True)
                return PlainTextResponse("Server error creating customer profile.", status_code=status.HTTP_200_OK)


            # Create an initial PENDING consent log since they messaged us
            initial_consent = ConsentLog(
                customer_id=customer.id,
                phone_number=from_number,
                business_id=business.id,
                method="customer_initiated_sms", # Indicates they messaged first
                status="pending", # Or 'pending_confirmation' if you always send an opt-in query
                sent_at=now_utc_aware, # Time of their first message
                # replied_at can be null until they reply to an opt-in query
            )
            db.add(initial_consent)
            initial_consent_created_this_request = True
            logger.info(f"{log_prefix}: Created new Customer ID {customer.id} and initial 'pending' ConsentLog ID {initial_consent.id if hasattr(initial_consent, 'id') else 'Pending'}.")
        else:
            logger.info(f"{log_prefix}: Matched Customer ID {customer.id} ({customer.customer_name}). Current opted_in flag from DB: {customer.opted_in}")

        # Check latest consent log status.
        latest_consent_log_for_check = db.query(ConsentLog).filter(
            ConsentLog.customer_id == customer.id,
            # ConsentLog.business_id == business.id # Filter by business if consent is per-business
        ).order_by(desc(ConsentLog.created_at)).first() # Or replied_at, or a combined latest timestamp logic

        if latest_consent_log_for_check and latest_consent_log_for_check.status == "opted_out":
            logger.warning(f"{log_prefix}: Customer {customer.id} ({from_number}) is OPTED_OUT based on ConsentLog. Discarding message.")
            if initial_consent_created_this_request: # If we just created the customer and a pending log
                db.rollback() # Rollback customer/consent creation
            return PlainTextResponse("Customer has opted out.", status_code=status.HTTP_200_OK)

        logger.info(f"{log_prefix}: Customer {customer.id} not explicitly opted-out by log. Latest ConsentLog status: '{latest_consent_log_for_check.status if latest_consent_log_for_check else 'None'}'.")

        # --- Conversation Handling ---
        conversation = db.query(ConversationModel).filter(
            ConversationModel.customer_id == customer.id,
            ConversationModel.business_id == business.id, # Important for multi-tenant
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

        # --- Log Inbound Message & Create Engagement ---
        inbound_message_record = Message(
            conversation_id=conversation.id, business_id=business.id, customer_id=customer.id,
            content=body_raw, message_type='inbound', status='received',
            sent_at=now_utc_aware, # Time customer's message was received by Twilio/us
            message_metadata={'twilio_sid': message_sid_from_twilio, 'source': 'customer_reply'}
        )
        db.add(inbound_message_record)
        try:
            db.flush()
        except Exception as e_flush_in_msg:
            db.rollback()
            logger.error(f"{log_prefix}: DB error flushing inbound message for customer {customer.id}: {e_flush_in_msg}", exc_info=True)
            return PlainTextResponse("Server error saving message.", status_code=status.HTTP_200_OK)


        engagement = Engagement(
            customer_id=customer.id, business_id=business.id, message_id=inbound_message_record.id,
            response=body_raw, ai_response=None, status="pending_review", created_at=now_utc_aware
        )
        db.add(engagement)
        try:
            db.flush()
        except Exception as e_flush_eng:
            db.rollback()
            logger.error(f"{log_prefix}: DB error flushing engagement for customer {customer.id}: {e_flush_eng}", exc_info=True)
            return PlainTextResponse("Server error creating engagement.", status_code=status.HTTP_200_OK)

        logger.info(f"{log_prefix}: Customer message logged. MsgID: {inbound_message_record.id}, EngID: {engagement.id}")

        # --- AI Response Generation ---
        ai_generated_reply_text: Optional[str] = None
        ai_payload_structured: Optional[dict] = None # Keep structured payload separate

        try:
            # AIService.generate_sms_response is expected to return a string
            ai_generated_reply_text = await ai_service.generate_sms_response(
                message=body_raw, business_id=business.id, customer_id=customer.id
            )
            if ai_generated_reply_text:
                # Create the structured payload dictionary
                ai_payload_structured = {
                    "text": ai_generated_reply_text, # Store the generated text here
                    "is_faq_answer": True,
                    "ai_can_reply_directly": True
                }
                # Store the JSON string representation in the database
                engagement.ai_response = json.dumps(ai_payload_structured)

                # Safely get text for logging preview from the structured payload
                ai_text_preview_content = ""
                if ai_payload_structured and isinstance(ai_payload_structured, dict) and "text" in ai_payload_structured:
                    ai_text_preview_content = ai_payload_structured.get("text", "")
                    if not isinstance(ai_text_preview_content, str): # Defensive check
                        ai_text_preview_content = str(ai_text_preview_content) # Ensure it's a string for slicing
                elif isinstance(ai_generated_reply_text, str):
                    # Fallback to the original generated text if structured payload wasn't created/valid
                    ai_text_preview_content = ai_generated_reply_text
                else:
                    # Last resort fallback
                    ai_text_preview_content = "AI response content unavailable for preview."

                # Use the extracted string content for logging the preview
                logger.info(f"{log_prefix}: AI draft for EngID {engagement.id}: '{ai_text_preview_content[:50]}...'")

            else:
                logger.warning(f"{log_prefix}: AI service returned no response text for EngID {engagement.id}")
        except Exception as ai_err:
            logger.error(f"{log_prefix}: AI response generation failed for EngID {engagement.id}: {ai_err}", exc_info=True)
            # ai_generated_reply_text remains None

        # --- AI Auto-Reply Logic (Flow B) ---
        # ONLY attempt auto-reply if AI successfully generated text AND it's enabled
        if business.enable_ai_faq_auto_reply and ai_generated_reply_text:
            logger.info(f"{log_prefix}: Business {business.id} has enable_ai_faq_auto_reply=True. Attempting AI auto-reply.")
            try:
                # Use the generated text content for sending
                message_content_to_send = ai_generated_reply_text # Start with the raw AI text

                # Append opt-in prompt if customer is newly created AND this is effectively their first *meaningful* interaction
                # and they are not yet opted in.
                if initial_consent_created_this_request and not customer.opted_in:
                    # Check latest consent again specifically for appending prompt
                    current_consent_for_prompt = db.query(ConsentLog).filter(ConsentLog.customer_id == customer.id).order_by(desc(ConsentLog.created_at)).first()
                    if not current_consent_for_prompt or current_consent_for_prompt.status == "pending":
                        message_content_to_send += "\n\nTo get more helpful info, reply YES to opt-in. Msg&Data rates may apply. Reply STOP to cancel."
                        logger.info(f"{log_prefix}: Appended opt-in prompt to AI reply for new/pending customer {customer.id}.")


                # Call send_sms with the explicit string content and flag as direct reply
                sent_message_sid = await twilio_service.send_sms(
                    to=customer.phone,
                    message_body=message_content_to_send, # Pass the explicitly constructed string
                    business=business,
                    is_direct_reply=True # This is a reply to an inbound message
                )

                if sent_message_sid:
                    engagement.status = "auto_replied_faq"
                    engagement.sent_at = datetime.now(pytz.UTC) # Record time AI reply was sent
                    logger.info(f"{log_prefix}: AI auto-reply sent for EngID {engagement.id}. SID: {sent_message_sid}. Status: '{engagement.status}'.")

                    # Log this AI auto-reply as an outbound Message
                    # Content for the Message record can be structured if desired
                    outbound_message_content_structured = {
                        "text": message_content_to_send, # Store the actual text sent
                        "is_faq_answer": True,
                        "appended_opt_in_prompt": (initial_consent_created_this_request and not customer.opted_in) # Track if prompt was added
                    }

                    outbound_message = Message(
                        conversation_id=conversation.id,
                        business_id=business.id,
                        customer_id=customer.id,
                        content=json.dumps(outbound_message_content_structured), # Store structured content as JSON string
                        message_type='outbound_ai_reply', # Specific type
                        status="sent", # Mark as sent
                        sent_at=engagement.sent_at, # Align timestamp
                        message_metadata={
                            'twilio_sid': sent_message_sid,
                            'source': 'ai_auto_reply_faq', # Clear source
                            'engagement_id': engagement.id,
                            'original_customer_message_sid': message_sid_from_twilio
                        }
                    )
                    db.add(outbound_message)
                    logger.info(f"{log_prefix}: Logged AI auto-reply as Message (ID to be assigned).")
                else: # Should not happen if send_sms raises on failure
                    logger.error(f"{log_prefix}: twilio_service.send_sms returned no SID for AI auto-reply (EngID {engagement.id}).")

            except HTTPException as http_send_exc:
                logger.error(f"{log_prefix}: HTTPException sending AI auto-reply for EngID {engagement.id}: {http_send_exc.detail} (Status: {http_send_exc.status_code})")
            except Exception as send_exc:
                logger.error(f"{log_prefix}: Unexpected error sending AI auto-reply for EngID {engagement.id}: {send_exc}", exc_info=True)

        elif not ai_generated_reply_text:
            logger.info(f"{log_prefix}: No AI response text available. AI Auto-reply skipped for EngID {engagement.id}.")
        elif not business.enable_ai_faq_auto_reply:
            logger.info(f"{log_prefix}: Business {business.id} has enable_ai_faq_auto_reply=False. AI Auto-reply skipped for EngID {engagement.id}. Draft (if any) saved in engagement.")


        # --- Owner Notification Logic (Flow A) ---
        # Notify owner if AI did NOT auto-reply (engagement status is still 'pending_review')
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
                # Enhanced deep link to include customer and engagement context
                deep_link_url = f"{settings.FRONTEND_APP_URL}/inbox/{business.slug}?activeCustomer={customer.id}&engagementId={engagement.id}"

                ai_draft_preview_for_notification = ""
                if engagement.ai_response:
                    try:
                        ai_data = json.loads(engagement.ai_response)
                        # Safely get text from the loaded JSON
                        ai_text = ai_data.get("text", "")
                        if not isinstance(ai_text, str): # Defensive check
                            ai_text = str(ai_text)
                        ai_draft_preview_for_notification = f"\nAI Draft: \"{ai_text[:40]}{'...' if len(ai_text) > 40 else ''}\""
                    except Exception as preview_err:
                        logger.warning(f"{log_prefix}: Could not parse ai_response JSON for preview: {preview_err}")

                notification_sms_body = (
                    f"AI Nudge: New SMS from {customer.customer_name} ({customer.phone}).\n"
                    f"Message: \"{body_raw[:70]}{'...' if len(body_raw) > 70 else ''}\""
                    f"{ai_draft_preview_for_notification}\n"
                    f"View & Reply: {deep_link_url}"
                )

                await twilio_service.send_sms(
                    to=business.business_phone_number,
                    message_body=notification_sms_body, # Use message_body keyword arg
                    business=business, # Send FROM this business's Twilio setup
                    is_direct_reply=False # Owner notification is a proactive message
                )
                logger.info(f"{log_prefix}: Owner SMS notification sent via TwilioService to {business.business_phone_number}.")

            except Exception as notify_err:
                logger.error(f"{log_prefix}: Failed to send owner notification SMS (via TwilioService): {notify_err}", exc_info=True)

        elif engagement.status != "pending_review":
            logger.info(f"{log_prefix}: Owner notification skipped because engagement status is '{engagement.status}'.")
        else: # Conditions for notification not met (e.g., business settings)
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
            # Twilio still expects a 200 OK response to acknowledge receipt of the webhook.
            # So, we log the error but return a generic success message to Twilio.
            return PlainTextResponse("Error saving interaction details.", status_code=status.HTTP_200_OK)

        return PlainTextResponse("SMS Received", status_code=status.HTTP_200_OK)

    except HTTPException as http_exc:
        logger.error(f"HTTPException in webhook: {http_exc.detail} (Status: {http_exc.status_code})", exc_info=True)
        # Ensure rollback if any DB operations happened before the HTTPException was raised by our code
        if db.is_active: # Check if session is active
            db.rollback()
        # Twilio expects a 200 OK even if we identify it as a bad request from their side
        # or an error on our side that we handle gracefully.
        return PlainTextResponse(f"Handled error: {http_exc.detail}", status_code=status.HTTP_200_OK)
    except Exception as e:
        current_form_data_str = str(dict(form_data))[:500] # Log part of form data for context
        logger.error(f"UNHANDLED EXCEPTION in webhook processing. SID: {message_sid_from_twilio}, From: {from_number_raw}, To: {to_number_raw}, Form Data (partial): {current_form_data_str}. Error: {e}", exc_info=True)
        if db.is_active:
            db.rollback()
        # For truly unhandled exceptions, Twilio might retry if it gets a 500.
        # However, often it's better to return 200 OK to stop retries if the issue is persistent or data-related.
        # Let's return 500 for now to indicate a server-side unhandled issue.
        return PlainTextResponse("Internal Server Error processing webhook", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        logger.info(f"=== Twilio Webhook: END /inbound processing for SID:{message_sid_from_twilio} ===")