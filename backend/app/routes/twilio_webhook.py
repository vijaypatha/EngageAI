# backend/app/routes/twilio_webhook.py

from datetime import datetime, timezone as dt_timezone # Keep existing import for timezone
import logging
import traceback # Ensure traceback is imported for detailed error logging
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Request, status, Response
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
    MessageStatusEnum 
)

from app.services.ai_service import AIService
from app.services.consent_service import ConsentService
from app.config import settings # Import settings to access FRONTEND_APP_URL
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
        message_sid_from_twilio = form_data.get("MessageSid", "N/A_FALLBACK_SID") # Provide a fallback

        log_prefix = f"INBOUND_SMS [SID:{message_sid_from_twilio}]"
        logger.info(f"{log_prefix}: From={from_number}(raw:{from_number_raw}), To={to_number}(raw:{to_number_raw}), Body='{body_raw}'")

        if not all([from_number, to_number, body_raw]):
            logger.error(f"{log_prefix}: Missing Twilio params. Form: {dict(form_data)}")
            return PlainTextResponse("Missing params", status_code=status.HTTP_200_OK)

        consent_log_response = await consent_service.process_sms_response(
            phone_number=from_number, response=body_lower
        )
        if consent_log_response:
            logger.info(f"{log_prefix}: Consent response handled for {from_number}.")
            return consent_log_response
        logger.info(f"{log_prefix}: Message from {from_number} not direct consent update. Proceeding.")

        business = db.query(BusinessProfile).filter(BusinessProfile.twilio_number == to_number).first()
        if not business:
            logger.error(f"{log_prefix}: No business for Twilio number {to_number}.")
            return PlainTextResponse("Receiving number not associated", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Routed to Business ID {business.id} ({business.business_name}).")

        customer = db.query(Customer).filter(
            Customer.phone == from_number, Customer.business_id == business.id
        ).first()

        now_utc_aware = datetime.now(pytz.UTC) 
        initial_consent_created_this_request = False
        if not customer:
            logger.info(f"{log_prefix}: New customer from {from_number}. Creating.")
            customer = Customer(
                phone=from_number, business_id=business.id,
                customer_name=f"Inbound Lead ({from_number})", opted_in=False, 
                created_at=now_utc_aware, lifecycle_stage="Lead", 
                pain_points="Unknown", interaction_history=f"First contact via SMS: {body_raw[:100]}"
            )
            db.add(customer)
            try:
                db.flush() 
            except Exception as e_flush_cust:
                db.rollback()
                logger.error(f"{log_prefix}: DB error flushing new customer {from_number}: {e_flush_cust}", exc_info=True)
                return PlainTextResponse("Server error creating customer profile.", status_code=status.HTTP_200_OK)

            initial_consent = ConsentLog(
                customer_id=customer.id, phone_number=from_number, business_id=business.id,
                method="customer_initiated_sms", status="pending", sent_at=now_utc_aware,
            )
            db.add(initial_consent)
            initial_consent_created_this_request = True
            logger.info(f"{log_prefix}: Created new Customer ID {customer.id} and initial 'pending' ConsentLog ID {initial_consent.id if hasattr(initial_consent, 'id') else 'Pending'}.")
        else:
            logger.info(f"{log_prefix}: Matched Customer ID {customer.id} ({customer.customer_name}). DB opted_in: {customer.opted_in}")

        latest_consent_log_for_check = db.query(ConsentLog).filter(
            ConsentLog.customer_id == customer.id,
        ).order_by(desc(ConsentLog.created_at)).first()

        if latest_consent_log_for_check and latest_consent_log_for_check.status == "opted_out":
            logger.warning(f"{log_prefix}: Customer {customer.id} is OPTED_OUT. Discarding.")
            if initial_consent_created_this_request: db.rollback() 
            return PlainTextResponse("Customer has opted out.", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Cust {customer.id} not opted-out. Latest ConsentLog: '{latest_consent_log_for_check.status if latest_consent_log_for_check else 'None'}'.")

        conversation = db.query(ConversationModel).filter(
            ConversationModel.customer_id == customer.id,
            ConversationModel.business_id == business.id, ConversationModel.status == 'active'
        ).first()
        if not conversation:
            conversation = ConversationModel(
                id=uuid.uuid4(), customer_id=customer.id, business_id=business.id,
                started_at=now_utc_aware, last_message_at=now_utc_aware, status='active'
            )
            db.add(conversation)
            try: db.flush()
            except Exception as e_flush_conv:
                db.rollback()
                logger.error(f"{log_prefix}: DB error flushing new conversation for cust {customer.id}: {e_flush_conv}", exc_info=True)
                return PlainTextResponse("Server error initializing conversation.", status_code=status.HTTP_200_OK)
            logger.info(f"{log_prefix}: New Conversation ID {conversation.id} for Cust {customer.id}.")
        else:
            conversation.last_message_at = now_utc_aware
            logger.info(f"{log_prefix}: Existing Conversation ID {conversation.id}. Updated last_message_at.")

        inbound_message_record = Message(
            conversation_id=conversation.id, business_id=business.id, customer_id=customer.id,
            content=body_raw, message_type='inbound', status='received',
            sent_at=now_utc_aware, message_metadata={'twilio_sid': message_sid_from_twilio, 'source': 'customer_reply'}
        )
        db.add(inbound_message_record)
        try: db.flush()
        except Exception as e_flush_in_msg:
            db.rollback()
            logger.error(f"{log_prefix}: DB error flushing inbound message for cust {customer.id}: {e_flush_in_msg}", exc_info=True)
            return PlainTextResponse("Server error saving message.", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Customer message logged. MsgID: {inbound_message_record.id}.")

        ai_response_data: Optional[Dict[str, Any]] = None
        engagement_status_after_ai = MessageStatusEnum.PENDING_REVIEW.value 
        ai_response_for_engagement_field: Optional[str] = None

        try:
            ai_response_data = await ai_service.generate_sms_response(
                message=body_raw, business_id=business.id, customer_id=customer.id
            )
        except Exception as ai_err:
            logger.error(f"{log_prefix}: AI response generation failed for biz {business.id}, cust {customer.id}: {ai_err}", exc_info=True)
        
        logger.info(f"{log_prefix}: AI response data from service: {ai_response_data}")
        logger.info(f"{log_prefix}: Business enable_ai_faq_auto_reply: {business.enable_ai_faq_auto_reply}")

        should_ai_reply_directly_as_faq = (
            ai_response_data and
            business.enable_ai_faq_auto_reply and
            ai_response_data.get("ai_should_reply_directly_as_faq", False)
        )
        logger.info(f"{log_prefix}: Calculated should_ai_reply_directly_as_faq: {should_ai_reply_directly_as_faq}")

        if should_ai_reply_directly_as_faq:
            logger.info(f"{log_prefix}: AI indicates direct FAQ reply. Attempting AI auto-reply.")
            ai_reply_text_for_sending = ai_response_data.get("text", "")
            if not ai_reply_text_for_sending:
                logger.error(f"{log_prefix}: AI indicated direct reply but no text found. Skipping auto-reply.")
                engagement_status_after_ai = MessageStatusEnum.PENDING_REVIEW.value
            else:
                message_content_to_send = ai_reply_text_for_sending; appended_opt_in_prompt_to_autopilot = False
                is_customer_pending_opt_in = not customer.opted_in and (not latest_consent_log_for_check or latest_consent_log_for_check.status == "pending")
                if is_customer_pending_opt_in:
                    message_content_to_send += "\n\nWant to stay in the loop? Reply YES to stay in touch. ❤️ Msg&Data rates may apply. Reply STOP to cancel."
                    appended_opt_in_prompt_to_autopilot = True
                    logger.info(f"{log_prefix}: Appended opt-in prompt to AI autopilot reply for pending cust {customer.id}.")
                try:
                    sent_message_sid = await twilio_service.send_sms(
                        to=customer.phone, message_body=message_content_to_send,
                        business=business, customer=customer, is_direct_reply=True 
                    )
                    if sent_message_sid:
                        engagement_status_after_ai = MessageStatusEnum.AUTO_REPLIED_FAQ.value
                        logger.info(f"{log_prefix}: AI auto-reply sent. SID: {sent_message_sid}. Status: {engagement_status_after_ai}.")
                        outbound_ai_message_content_structured = {
                            "text": ai_reply_text_for_sending, "is_faq_answer": True,
                            "source": "faq_autopilot", "appended_opt_in_prompt": appended_opt_in_prompt_to_autopilot
                        }
                        outbound_message = Message(
                            conversation_id=conversation.id, business_id=business.id, customer_id=customer.id,
                            content=json.dumps(outbound_ai_message_content_structured),
                            message_type=MessageTypeEnum.OUTBOUND_AI_REPLY.value, status=MessageStatusEnum.SENT.value,
                            sent_at=datetime.now(pytz.UTC), message_metadata={
                                'twilio_sid': sent_message_sid, 'source': 'faq_autopilot', 
                                'original_customer_message_sid': message_sid_from_twilio
                            }
                        )
                        db.add(outbound_message); logger.info(f"{log_prefix}: Logged AI auto-reply as Message.")
                    else: 
                        logger.error(f"{log_prefix}: twilio_service.send_sms returned no SID for AI auto-reply.")
                        engagement_status_after_ai = MessageStatusEnum.PENDING_REVIEW.value
                except Exception as send_exc:
                    logger.error(f"{log_prefix}: Unexpected error sending AI auto-reply: {send_exc}", exc_info=True)
                    engagement_status_after_ai = MessageStatusEnum.PENDING_REVIEW.value
        
        if engagement_status_after_ai == MessageStatusEnum.PENDING_REVIEW.value and ai_response_data and ai_response_data.get("text"):
            ai_response_for_engagement_field = json.dumps({
                "text": ai_response_data.get("text"), "is_faq_answer": ai_response_data.get("is_faq_answer", False),
            })
            logger.info(f"{log_prefix}: AI response prepared for eng draft: '{ai_response_data.get('text', '')[:50]}...'")
        elif engagement_status_after_ai == MessageStatusEnum.PENDING_REVIEW.value:
             logger.info(f"{log_prefix}: No AI response available or not suitable for draft, engagement pending review.")

        engagement = Engagement(
            customer_id=customer.id, business_id=business.id, message_id=inbound_message_record.id,
            response=body_raw, ai_response=ai_response_for_engagement_field, 
            status=engagement_status_after_ai, created_at=now_utc_aware,
            sent_at=datetime.now(pytz.UTC) if engagement_status_after_ai == MessageStatusEnum.AUTO_REPLIED_FAQ.value else None
        )
        db.add(engagement)
        try: db.flush(); logger.info(f"{log_prefix}: Eng record created. EngID: {engagement.id}, Status: {engagement.status}")
        except Exception as e_flush_eng:
            db.rollback()
            logger.error(f"{log_prefix}: DB error flushing eng for cust {customer.id}: {e_flush_eng}", exc_info=True)
            return PlainTextResponse("Server error creating engagement record.", status_code=status.HTTP_200_OK)

        # --- START OF LOGGING FOR OWNER NOTIFICATION ---
        logger.info(f"{log_prefix}: --- Owner Notification Check ---")
        logger.info(f"{log_prefix}: business.notify_owner_on_reply_with_link: {business.notify_owner_on_reply_with_link} (Type: {type(business.notify_owner_on_reply_with_link)})")
        logger.info(f"{log_prefix}: business.business_phone_number: {business.business_phone_number}")
        logger.info(f"{log_prefix}: business.slug: {business.slug}")
        logger.info(f"{log_prefix}: engagement.status: {engagement.status} (Expected: {MessageStatusEnum.PENDING_REVIEW.value})")
        logger.info(f"{log_prefix}: settings.FRONTEND_APP_URL: {settings.FRONTEND_APP_URL}")
        
        should_notify_owner_now = (
            business.notify_owner_on_reply_with_link and
            business.business_phone_number and
            business.slug and
            engagement.status == MessageStatusEnum.PENDING_REVIEW.value 
        )
        logger.info(f"{log_prefix}: Result of should_notify_owner_now: {should_notify_owner_now}")
        # --- END OF LOGGING FOR OWNER NOTIFICATION ---

        if should_notify_owner_now:
            logger.info(f"{log_prefix}: CONDITION MET - Preparing owner notification for EngID {engagement.id}.")
            try:
                deep_link_url = f"{settings.FRONTEND_APP_URL}/inbox/{business.slug}?activeCustomer={customer.id}&engagementId={engagement.id}"
                logger.info(f"{log_prefix}:   Constructed deep_link_url: '{deep_link_url}'")

                ai_draft_preview_for_notification = ""
                if engagement.ai_response:
                    try:
                        ai_data_for_preview = json.loads(engagement.ai_response)
                        ai_text_for_preview = ai_data_for_preview.get("text", "")
                        if not isinstance(ai_text_for_preview, str): 
                            ai_text_for_preview = str(ai_text_for_preview)
                        ai_draft_preview_for_notification = f"\nAI Draft: \"{ai_text_for_preview[:40]}{'...' if len(ai_text_for_preview) > 40 else ''}\""
                        logger.info(f"{log_prefix}:   AI draft preview for notification: '{ai_draft_preview_for_notification}'")
                    except Exception as preview_err:
                        logger.warning(f"{log_prefix}:   Could not parse engagement.ai_response JSON for notification preview: {preview_err}. Raw ai_response: {engagement.ai_response}")
                        ai_draft_preview_for_notification = "\nAI Draft: [Preview not available]"
                else:
                    logger.info(f"{log_prefix}:   No AI draft (engagement.ai_response is None/empty) for preview in notification.")

                notification_sms_body = (
                    f"AI Nudge: New SMS from {customer.customer_name} ({customer.phone}).\n"
                    f"Message: \"{body_raw[:70]}{'...' if len(body_raw) > 70 else ''}\""
                    f"{ai_draft_preview_for_notification}\n"
                    f"View & Reply: {deep_link_url}"
                )
                logger.info(f"{log_prefix}:   CONSTRUCTED owner notification_sms_body: '{notification_sms_body}'")
                logger.info(f"{log_prefix}:   Attempting to send owner notification SMS to: {business.business_phone_number}")
                
                await twilio_service.send_sms(
                    to=business.business_phone_number,
                    message_body=notification_sms_body, 
                    business=business, 
                    customer=customer, 
                    is_direct_reply=False,
                    is_owner_notification=True
                )
                logger.info(f"{log_prefix}:   Owner SMS notification API call to TwilioService initiated for {business.business_phone_number}.")
            except Exception as notify_err:
                logger.error(f"{log_prefix}:   EXCEPTION during owner notification sending: {notify_err}", exc_info=True)
        elif engagement.status != MessageStatusEnum.PENDING_REVIEW.value: # Check against enum value
            logger.info(f"{log_prefix}: Owner notification skipped because engagement status is '{engagement.status}'.")
        else: 
            logger.info(
                f"{log_prefix}: CONDITION NOT MET - Owner notification skipped. "
                f"Notify: {business.notify_owner_on_reply_with_link}, "
                f"OwnerPhone: {'Set' if business.business_phone_number else 'Not Set'}, "
                f"Slug: {'Set' if business.slug else 'Not Set'}, "
                f"EngStatus: {engagement.status}"
            )
        try:
            db.commit(); logger.info(f"{log_prefix}: Database changes committed successfully.")
        except Exception as db_commit_err:
            db.rollback()
            logger.error(f"{log_prefix}: Final DB commit failed: {db_commit_err}", exc_info=True)
            return PlainTextResponse("Error saving interaction details.", status_code=status.HTTP_200_OK)

        return PlainTextResponse("SMS Received", status_code=status.HTTP_200_OK)

    except HTTPException as http_exc:
        logger.error(f"HTTPException in webhook: {http_exc.detail} (Status: {http_exc.status_code})", exc_info=True)
        if db.is_active: db.rollback()
        return PlainTextResponse(f"Handled error: {http_exc.detail}", status_code=status.HTTP_200_OK)
    except Exception as e:
        current_form_data_str = str(dict(form_data))[:500] 
        logger.error(f"UNHANDLED EXCEPTION in webhook processing. SID: {message_sid_from_twilio}, From: {from_number_raw}, To: {to_number_raw}, Form Data (partial): {current_form_data_str}. Error: {e}", exc_info=True)
        if db.is_active: db.rollback()
        return PlainTextResponse("Internal Server Error processing webhook", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        logger.info(f"=== Twilio Webhook: END /inbound processing for SID:{message_sid_from_twilio} ===")