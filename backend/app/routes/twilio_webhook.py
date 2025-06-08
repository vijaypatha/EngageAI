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
    CoPilotNudge, # Import CoPilotNudge
    NudgeTypeEnum # Import NudgeTypeEnum
)

from app.services.ai_service import AIService
from app.services.consent_service import ConsentService
from app.config import settings
from app.services.twilio_service import TwilioService
from app.services.copilot_nudge_generation_service import CoPilotNudgeGenerationService
# Import the new Celery task
from app.celery_tasks import trigger_strategic_engagement_plan_generation_task

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
    inbound_message_record_id_for_nudges: Optional[int] = None # To store the ID of the saved inbound message

    twilio_service = TwilioService(db=db)
    ai_service = AIService(db=db)
    consent_service = ConsentService(db=db)
    # Nudge generation service instantiated later if needed

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
        message_sid_from_twilio = form_data.get("MessageSid", "N/A_FALLBACK_SID")

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
                db.rollback(); logger.error(f"{log_prefix}: DB error flushing new conversation for cust {customer.id}: {e_flush_conv}", exc_info=True)
                return PlainTextResponse("Server error initializing conversation.", status_code=status.HTTP_200_OK)
            logger.info(f"{log_prefix}: New Conversation ID {conversation.id} for Cust {customer.id}.")
        else:
            conversation.last_message_at = now_utc_aware
            logger.info(f"{log_prefix}: Existing Conversation ID {conversation.id}. Updated last_message_at.")

        inbound_message_record = Message(
            conversation_id=conversation.id, business_id=business.id, customer_id=customer.id,
            content=body_raw, message_type=MessageTypeEnum.INBOUND.value, status=MessageStatusEnum.RECEIVED.value,
            sent_at=now_utc_aware, message_metadata={'twilio_sid': message_sid_from_twilio, 'source': 'customer_reply'}
        )
        db.add(inbound_message_record)
        try:
            db.flush()
            inbound_message_record_id_for_nudges = inbound_message_record.id # Store ID after successful flush
        except Exception as e_flush_in_msg:
            db.rollback(); logger.error(f"{log_prefix}: DB error flushing inbound message for cust {customer.id}: {e_flush_in_msg}", exc_info=True)
            return PlainTextResponse("Server error saving message.", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Customer message logged. MsgID: {inbound_message_record_id_for_nudges}.")

        ai_response_data: Optional[Dict[str, Any]] = None
        engagement_status_after_ai = MessageStatusEnum.PENDING_REVIEW.value
        ai_response_for_engagement_field: Optional[str] = None

        try:
            ai_response_data = await ai_service.generate_sms_response(
                message=body_raw, business_id=business.id, customer_id=customer.id
            )
        except Exception as ai_err:
            logger.error(f"{log_prefix}: AI response generation for engagement draft failed: {ai_err}", exc_info=True)
        
        # ... (Your existing FAQ Autopilot and Engagement creation logic) ...
        if ai_response_data and business.enable_ai_faq_auto_reply and ai_response_data.get("ai_should_reply_directly_as_faq", False):
            # ... (FAQ auto-reply logic as before) ...
            logger.info(f"{log_prefix}: AI indicates direct FAQ reply. Attempting AI auto-reply.")
            ai_reply_text_for_sending = ai_response_data.get("text", "")
            if not ai_reply_text_for_sending:
                logger.error(f"{log_prefix}: AI indicated direct reply but no text found. Skipping auto-reply.")
            else:
                # ... (SMS sending logic for FAQ auto-reply) ...
                engagement_status_after_ai = MessageStatusEnum.AUTO_REPLIED_FAQ.value # If successful
        
        if engagement_status_after_ai == MessageStatusEnum.PENDING_REVIEW.value and ai_response_data and ai_response_data.get("text"):
            ai_response_for_engagement_field = json.dumps({
                "text": ai_response_data.get("text"), "is_faq_answer": ai_response_data.get("is_faq_answer", False),
            })
        
        engagement = Engagement(
            customer_id=customer.id, business_id=business.id, message_id=inbound_message_record_id_for_nudges,
            response=body_raw, ai_response=ai_response_for_engagement_field,
            status=engagement_status_after_ai, created_at=now_utc_aware,
            sent_at=datetime.now(pytz.UTC) if engagement_status_after_ai == MessageStatusEnum.AUTO_REPLIED_FAQ.value else None
        )
        db.add(engagement); db.flush()
        logger.info(f"{log_prefix}: Engagement record created/updated. EngID: {engagement.id}, Status: {engagement.status}")

        # --- Owner Notification Logic (if engagement is PENDING_REVIEW) ---
        if engagement.status == MessageStatusEnum.PENDING_REVIEW.value:
            if business.notify_owner_on_reply_with_link and business.business_phone_number and business.slug:
                # ... (Owner notification SMS logic as before) ...
                pass # Placeholder for brevity
        
        # --- Commit primary message and engagement processing ---
        try:
            db.commit()
            logger.info(f"{log_prefix}: Main message/engagement processing committed.")
        except Exception as db_commit_err:
            db.rollback()
            logger.error(f"{log_prefix}: Main DB commit failed: {db_commit_err}", exc_info=True)
            return PlainTextResponse("Error saving interaction details.", status_code=status.HTTP_200_OK)

        # --- NUDGE GENERATION LOGIC ---
        nudge_generation_service = CoPilotNudgeGenerationService(db)
        
        # 1. Detect Potential Timed Commitments (as before)
        potential_timed_event_nudge_created = False
        if inbound_message_record_id_for_nudges:
            try:
                logger.info(f"{log_prefix}: Checking for POTENTIAL_TARGETED_EVENT from MsgID {inbound_message_record_id_for_nudges}.")
                created_timed_nudges = nudge_generation_service.detect_potential_timed_commitments(
                    business_id=business.id,
                    specific_message_id=inbound_message_record_id_for_nudges
                )
                if created_timed_nudges:
                    potential_timed_event_nudge_created = True
                    logger.info(f"{log_prefix}: Created {len(created_timed_nudges)} POTENTIAL_TARGETED_EVENT nudges.")
            except Exception as e_timed_nudge:
                logger.error(f"{log_prefix}: Error in detect_potential_timed_commitments: {e_timed_nudge}", exc_info=True)

        # 2. NEW LOGIC FOR STRATEGIC PLAN NUDGES (if appropriate)
        # Condition:
        # - Engagement is still PENDING_REVIEW (AI didn't auto-reply as FAQ)
        # - AND a POTENTIAL_TARGETED_EVENT nudge was NOT just created for this message (to avoid duplicate AI suggestions for the same message)
        # - AND the message is not a simple sentiment that would be handled by generate_sentiment_nudges_task
        
        # Simple heuristic: Check if the AI response draft (for engagement) is empty or very short,
        # implying it might be a nuanced reply needing a strategic plan.
        # Also, ensure it's not already handled by sentiment or timed event detection.
        # A more robust check would be needed for production (e.g., LLM call for intent).

        is_handled_by_sentiment_or_event = False # Placeholder for this check
        # In a real scenario, you'd check if sentiment or timed event nudges were created for this message.
        # For this example, we'll rely on potential_timed_event_nudge_created.
        # You might also need to query if a sentiment nudge was created if that runs separately.

        if engagement.status == MessageStatusEnum.PENDING_REVIEW.value and not potential_timed_event_nudge_created:
            # Fetch the last outbound message from the business in this conversation for context
            last_business_message_obj = db.query(Message)\
                .filter(Message.conversation_id == conversation.id, Message.message_type == MessageTypeEnum.OUTBOUND.value)\
                .order_by(Message.sent_at.desc())\
                .first()
            last_business_message_text = last_business_message_obj.content if last_business_message_obj else "No previous business message found."

            trigger_data_for_plan = {
                "customer_reply": body_raw,
                "last_business_message": last_business_message_text,
                "original_message_id": inbound_message_record_id_for_nudges # Link to the inbound message
            }
            
            logger.info(f"{log_prefix}: Conditions met for strategic plan generation. Dispatching Celery task. MsgID: {inbound_message_record_id_for_nudges}")
            try:
                trigger_strategic_engagement_plan_generation_task.delay(
                    business_id=business.id,
                    customer_id=customer.id,
                    trigger_data=trigger_data_for_plan
                    # business_objective could be passed if determined here
                )
                logger.info(f"{log_prefix}: Celery task for strategic plan generation dispatched for CustID {customer.id}.")
            except Exception as celery_dispatch_err:
                logger.error(f"{log_prefix}: Failed to dispatch Celery task for strategic plan: {celery_dispatch_err}", exc_info=True)
        else:
            logger.info(f"{log_prefix} Skipping strategic plan generation. Eng Status: {engagement.status}, TimedEventNudgeCreated: {potential_timed_event_nudge_created}")


        return PlainTextResponse("SMS Received", status_code=status.HTTP_200_OK)

    except HTTPException as http_exc:
        # ... (existing HTTPException handling) ...
        logger.error(f"HTTPException in webhook: {http_exc.detail} (Status: {http_exc.status_code})", exc_info=True)
        if db.is_active: db.rollback()
        return PlainTextResponse(f"Handled error: {http_exc.detail}", status_code=status.HTTP_200_OK)
    except Exception as e:
        # ... (existing general Exception handling) ...
        current_form_data_str = str(dict(form_data))[:500] 
        logger.error(f"UNHANDLED EXCEPTION in webhook processing. SID: {message_sid_from_twilio}, From: {from_number_raw}, To: {to_number_raw}, Form Data (partial): {current_form_data_str}. Error: {e}", exc_info=True)
        if db.is_active: db.rollback()
        return PlainTextResponse("Internal Server Error processing webhook", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        logger.info(f"=== Twilio Webhook: END /inbound processing for SID:{message_sid_from_twilio} ===")

