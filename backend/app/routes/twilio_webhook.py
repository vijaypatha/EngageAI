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
    NudgeTypeEnum, # Import NudgeTypeEnum
    OptInStatus
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
    message_sid_from_twilio = form_data.get("MessageSid", f"fallback-sid-{uuid.uuid4()}")
    from_number_raw = form_data.get("From", "")
    to_number_raw = form_data.get("To", "")
    form_data = {}
    inbound_message_record_id_for_nudges: Optional[int] = None

    # Instantiate all services
    twilio_service = TwilioService(db=db)
    ai_service = AIService(db=db)
    consent_service = ConsentService(db=db)
    
    log_prefix = f"INBOUND_SMS [SID:{message_sid_from_twilio}]"

    try:
        form_data = await request.form()
        from_number_raw = form_data.get("From", "")
        to_number_raw = form_data.get("To", "")

        from_number = normalize_phone(from_number_raw)
        to_number = normalize_phone(to_number_raw)
        
        body_raw = form_data.get("Body", "").strip()
        body_lower = body_raw.lower()
        
        logger.info(f"{log_prefix}: From={from_number}, To={to_number}, Body='{body_raw}'")

        if not all([from_number, to_number, body_raw]):
            logger.error(f"{log_prefix}: Missing Twilio params.")
            return PlainTextResponse("Missing params", status_code=status.HTTP_200_OK)

        # Priority 1: Handle direct STOP/YES consent replies
        consent_log_response = await consent_service.process_sms_response(phone_number=from_number, response=body_lower)
        if consent_log_response:
            logger.info(f"{log_prefix}: Request handled by consent service. Terminating.")
            return consent_log_response
        
        logger.info(f"{log_prefix}: Message not a direct consent update. Proceeding.")

        # Find business
        business = db.query(BusinessProfile).filter(BusinessProfile.twilio_number == to_number).first()
        if not business:
            logger.error(f"{log_prefix}: No business for Twilio number {to_number}.")
            return PlainTextResponse("Receiving number not associated", status_code=status.HTTP_200_OK)
        
        logger.info(f"{log_prefix}: Routed to Business ID {business.id}.")

        # Find or Create Customer
        now_utc_aware = datetime.now(pytz.UTC)
        customer = db.query(Customer).filter(Customer.phone == from_number, Customer.business_id == business.id).first()

        if not customer:
            logger.info(f"{log_prefix}: New customer from {from_number}. Creating.")
            customer = Customer(
                phone=from_number, business_id=business.id,
                customer_name=f"Inbound Lead ({from_number})",
                # MODIFICATION: Use the new OptInStatus enum
                sms_opt_in_status=OptInStatus.NOT_SET.value,
                created_at=now_utc_aware, lifecycle_stage="Lead",
                pain_points="Unknown", interaction_history=f"First contact via SMS: {body_raw[:100]}"
            )
            db.add(customer)
            db.flush() # Flush to get customer ID

            # Create initial pending consent log for new inbound leads
            initial_consent = ConsentLog(
                customer_id=customer.id, phone_number=from_number, business_id=business.id,
                method="customer_initiated_sms", status="pending", sent_at=now_utc_aware,
            )
            db.add(initial_consent)
            logger.info(f"{log_prefix}: Created new Customer ID {customer.id} and initial 'pending' ConsentLog.")
        else:
            logger.info(f"{log_prefix}: Matched Customer ID {customer.id}.")

        # MODIFICATION: Add check to stop processing for opted-out customers
        if customer.sms_opt_in_status == OptInStatus.OPTED_OUT.value:
            logger.warning(f"{log_prefix}: Customer {customer.id} is OPTED_OUT. Discarding message.")
            return PlainTextResponse("Customer has opted out.", status_code=status.HTTP_200_OK)

        # Find or Create Conversation and Log Inbound Message
        conversation = db.query(ConversationModel).filter(ConversationModel.customer_id == customer.id, ConversationModel.status == 'active').first()
        if not conversation:
            conversation = ConversationModel(id=uuid.uuid4(), customer_id=customer.id, business_id=business.id, status='active', started_at=now_utc_aware)
            db.add(conversation)
        conversation.last_message_at = now_utc_aware
        db.flush()

        inbound_message_record = Message(
            conversation_id=conversation.id, business_id=business.id, customer_id=customer.id,
            content=body_raw, message_type=MessageTypeEnum.INBOUND.value, status=MessageStatusEnum.RECEIVED.value,
            sent_at=now_utc_aware, message_metadata={'twilio_sid': message_sid_from_twilio, 'source': 'customer_reply'}
        )
        db.add(inbound_message_record)
        db.flush()
        inbound_message_record_id_for_nudges = inbound_message_record.id
        logger.info(f"{log_prefix}: Customer message logged. MsgID: {inbound_message_record_id_for_nudges}.")

        # --- MODIFICATION: AI Autopilot & Engagement Logic ---
        ai_handled_reply = False
        ai_response_text = None
        engagement_status = MessageStatusEnum.PENDING_REVIEW # Default
        ai_response_for_engagement_field = None

        # Step 3: AI Autopilot Decision Point
        if business.enable_ai_faq_auto_reply:
            logger.info(f"{log_prefix}: AI Autopilot is ON. Analyzing message.")
            try:
                ai_response_data = await ai_service.generate_sms_response(message=body_raw, customer_id=customer.id, business_id=business.id)
                ai_response_text = ai_response_data.get("text")
                ai_response_for_engagement_field = json.dumps(ai_response_data) if ai_response_data else None

                # Step 4A: Automated FAQ Reply Path
                if ai_response_data.get("ai_should_reply_directly_as_faq") and ai_response_text:
                    logger.info(f"{log_prefix}: AI identified FAQ. Attempting auto-reply.")
                    reply_sid = await twilio_service.send_sms(to=customer.phone, message_body=ai_response_text, business=business, customer=customer, is_direct_reply=True)
                    outbound_auto_reply = Message(
                        conversation_id=conversation.id, business_id=business.id, customer_id=customer.id,
                        content=ai_response_text, message_type=MessageTypeEnum.OUTBOUND.value, status=MessageStatusEnum.SENT.value,
                        sent_at=datetime.now(pytz.UTC), message_metadata={'source': 'ai_faq_auto_reply', 'twilio_sid': reply_sid}
                    )
                    db.add(outbound_auto_reply)
                    engagement_status = MessageStatusEnum.AUTO_REPLIED_FAQ
                    ai_handled_reply = True
                    logger.info(f"{log_prefix}: AI Auto-reply sent successfully. SID: {reply_sid}")
            except Exception as e:
                logger.error(f"{log_prefix}: Error during AI Autopilot processing: {e}", exc_info=True)
        else: # If autopilot is off, still get the AI draft for manual review
             try:
                ai_response_data = await ai_service.generate_sms_response(message=body_raw, customer_id=customer.id, business_id=business.id)
                ai_response_for_engagement_field = json.dumps(ai_response_data) if ai_response_data else None
             except Exception as ai_err:
                logger.error(f"{log_prefix}: AI response generation for engagement draft failed: {ai_err}", exc_info=True)


        # Create the Engagement record
        engagement = Engagement(
            customer_id=customer.id, business_id=business.id, message_id=inbound_message_record_id_for_nudges,
            response=body_raw, ai_response=ai_response_for_engagement_field,
            status=engagement_status, created_at=now_utc_aware,
            sent_at=datetime.now(pytz.UTC) if engagement_status == MessageStatusEnum.AUTO_REPLIED_FAQ else None
        )
        db.add(engagement)
        logger.info(f"{log_prefix}: Engagement record created. EngID: {engagement.id}, Status: {engagement.status}")

        # Owner Notification Logic (PRESERVED)
        if engagement.status == MessageStatusEnum.PENDING_REVIEW:
            if business.notify_owner_on_reply_with_link and business.business_phone_number and business.slug:
                logger.info(f"{log_prefix}: Notifying business owner for manual review.")
                # Updated notification link
                notification_link = f"{settings.FRONTEND_APP_URL}/inbox/{business.slug}?activeCustomer={customer.id}"
                notification_msg = f"AI Nudge: New reply from {customer.customer_name or customer.phone}. View: {notification_link}"
                await twilio_service.send_sms(to=business.business_phone_number, message_body=notification_msg, business=business, is_owner_notification=True)

        # Commit primary transaction (moved before opt-in logic that might also commit)
        db.commit()
        logger.info(f"{log_prefix}: Main transaction committed (customer, message, engagement).")


        # --- Nudge and Strategy Logic (PRESERVED) ---
        # This section might also commit if it creates nudges, so it's fine here.
        nudge_generation_service = CoPilotNudgeGenerationService(db)
        potential_timed_event_nudge_created = False
        if inbound_message_record_id_for_nudges:
            try:
                created_timed_nudges = nudge_generation_service.detect_potential_timed_commitments(business_id=business.id, specific_message_id=inbound_message_record_id_for_nudges)
                if created_timed_nudges:
                    potential_timed_event_nudge_created = True
                    logger.info(f"{log_prefix}: Created {len(created_timed_nudges)} POTENTIAL_TARGETED_EVENT nudges.")
            except Exception as e:
                logger.error(f"{log_prefix}: Error in detect_potential_timed_commitments: {e}", exc_info=True)

        if engagement.status == MessageStatusEnum.PENDING_REVIEW and not potential_timed_event_nudge_created:
            last_business_message = db.query(Message).filter(Message.conversation_id == conversation.id, Message.message_type == MessageTypeEnum.OUTBOUND.value).order_by(Message.sent_at.desc()).first()
            trigger_data = {"customer_reply": body_raw, "last_business_message": last_business_message.content if last_business_message else "No previous message.", "original_message_id": inbound_message_record_id_for_nudges}
            logger.info(f"{log_prefix}: Dispatching strategic plan generation task for CustID {customer.id}")
            trigger_strategic_engagement_plan_generation_task.delay(business_id=business.id, customer_id=customer.id, trigger_data=trigger_data)
        

        # --- MODIFIED OPT-IN TRIGGER LOGIC ---
        should_send_opt_in = False
        if customer: # Ensure customer object exists
            # Refresh customer object to get latest state if changed by prior operations in this session
            db.refresh(customer)

            latest_consent_for_opt_in_trigger = db.query(ConsentLog).filter(
                ConsentLog.customer_id == customer.id
            ).order_by(desc(ConsentLog.created_at)).first()

            # Check if customer is not opted in and their status implies they could be prompted
            # OptInStatus.NOT_SET means they've never interacted with consent system (new customer)
            # OptInStatus.PENDING means they were sent an opt-in but haven't replied (or initial state for new inbound)
            # 'pending_confirmation' is an older status that might still be in use or equivalent to PENDING
            if not customer.opted_in and \
               (customer.sms_opt_in_status == OptInStatus.NOT_SET.value or \
                customer.sms_opt_in_status == OptInStatus.PENDING.value):

                # Further check on ConsentLog: if the latest log is missing or is 'pending' or 'not_set'
                if not latest_consent_for_opt_in_trigger or \
                   latest_consent_for_opt_in_trigger.status in [OptInStatus.NOT_SET.value, OptInStatus.PENDING.value, 'pending_confirmation']:
                    should_send_opt_in = True

        if should_send_opt_in:
            logger.info(f"{log_prefix}: Customer {customer.id} requires opt-in. sms_opt_in_status: '{customer.sms_opt_in_status}', opted_in flag: {customer.opted_in}. Triggering double opt-in SMS.")
            try:
                # send_double_optin_sms internally checks if an opt-in message was sent recently to avoid spamming.
                await consent_service.send_double_optin_sms(customer_id=customer.id, business_id=business.id)
                # send_double_optin_sms also commits its own transaction for ConsentLog updates.
            except Exception as opt_in_exc:
                logger.error(f"{log_prefix}: Error sending double opt-in SMS for customer {customer.id}: {opt_in_exc}", exc_info=True)
        else:
            logger.info(f"{log_prefix}: Opt-in SMS not required for customer {customer.id} (Opted-in: {customer.opted_in}, SMS Opt-in Status: {customer.sms_opt_in_status}, Latest ConsentLog: {latest_consent_for_opt_in_trigger.status if latest_consent_for_opt_in_trigger else 'None'}).")

        # Final commit for any changes not covered by specific service calls that commit themselves.
        # For example, if nudge generation doesn't commit but adds to session.
        # Most critical objects (Customer, Message, Engagement, initial ConsentLog) were committed earlier.
        # Opt-in service commits its own ConsentLog updates.
        if db.dirty or db.new or db.deleted: # Check if there's anything to commit
            logger.info(f"{log_prefix}: Committing final session changes before returning.")
            db.commit()

        return PlainTextResponse("SMS Received", status_code=status.HTTP_200_OK)

    except Exception as e:
        current_form_data_str = str(dict(form_data))[:500]
        logger.error(f"UNHANDLED EXCEPTION in webhook. SID: {message_sid_from_twilio}, From: {from_number_raw}, To: {to_number_raw}, Form (partial): {current_form_data_str}. Error: {e}", exc_info=True)
        if 'db' in locals() and db.is_active:
            db.rollback()
        return PlainTextResponse("Internal Server Error", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        logger.info(f"=== Twilio Webhook: END /inbound processing for SID:{message_sid_from_twilio} ===")