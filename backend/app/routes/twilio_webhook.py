# backend/app/routes/twilio_webhook.py

from datetime import datetime, timezone
import logging
import traceback
import uuid 

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
import pytz 

from app.database import get_db
from app.models import (
    BusinessProfile,
    Customer,
    Engagement,
    Message,
    Conversation as ConversationModel,
    ConsentLog
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
    # Initialize TwilioService directly. If you have a Depends for it, that's also fine.
    twilio_service = TwilioService(db=db) # Pass the db session

    try:
        form_data = await request.form()
        from_number_raw = form_data.get("From", "")
        to_number_raw = form_data.get("To", "")
        
        try:
            from_number = normalize_phone(from_number_raw)
        except ValueError as e:
            logger.error(f"INBOUND_SMS [SID_UNKNOWN]: Invalid 'From' phone number format: '{from_number_raw}'. Error: {e}")
            # Twilio expects a 200 OK even for errors it considers non-retryable at this stage.
            # Or an empty TwiML <Response/> if you want Twilio to do nothing else.
            return PlainTextResponse(f"Invalid 'From' number format: {from_number_raw}", status_code=status.HTTP_200_OK)

        try:
            to_number = normalize_phone(to_number_raw)
        except ValueError as e:
            logger.error(f"INBOUND_SMS [SID_UNKNOWN]: Invalid 'To' phone number format: '{to_number_raw}'. Error: {e}")
            return PlainTextResponse(f"Invalid 'To' number format: {to_number_raw}", status_code=status.HTTP_200_OK)

        body_raw = form_data.get("Body", "").strip()
        body_lower = body_raw.lower()
        message_sid_from_twilio = form_data.get("MessageSid", "N/A")
        
        log_prefix = f"INBOUND_SMS [SID:{message_sid_from_twilio}]"
        logger.info(f"{log_prefix}: From={from_number}(raw:{from_number_raw}), To={to_number}(raw:{to_number_raw}), Body='{body_raw}'")

        if not all([from_number, to_number, body_raw]):
            logger.error(f"{log_prefix}: Missing required Twilio parameters. Form: {dict(form_data)}")
            return PlainTextResponse("Missing parameters", status_code=status.HTTP_200_OK)

        # --- Consent Processing Logic ---
        consent_service = ConsentService(db)
        consent_response = await consent_service.process_sms_response(
            phone_number=from_number,
            response=body_lower
        )
        if consent_response:
            logger.info(f"{log_prefix}: Consent response handled by ConsentService for {from_number}.")
            return consent_response
        logger.info(f"{log_prefix}: Message from {from_number} not a direct consent update by service. Proceeding.")

        # --- Regular Message Handling ---
        business = db.query(BusinessProfile).filter(BusinessProfile.twilio_number == to_number).first()
        if not business:
            logger.error(f"{log_prefix}: No business found for Twilio number {to_number}. Cannot route.")
            return PlainTextResponse("Receiving number not associated", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Routed to Business ID {business.id} ({business.business_name}).")

        customer = db.query(Customer).filter(
            Customer.phone == from_number,
            Customer.business_id == business.id
        ).first()
        if not customer:
            logger.warning(f"{log_prefix}: No customer record for {from_number} in Business ID {business.id}.")
            return PlainTextResponse("Customer not registered with this business", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Matched Customer ID {customer.id} ({customer.customer_name}).")

        if not customer.opted_in:
             logger.warning(f"{log_prefix}: Customer {customer.id} ({from_number}) is NOT opted-in. Discarding.")
             return PlainTextResponse("Customer not opted-in", status_code=status.HTTP_200_OK)
        logger.info(f"{log_prefix}: Customer {customer.id} is opted-in. Processing message.")

        now_utc = datetime.now(pytz.UTC) 
        conversation = db.query(ConversationModel).filter(
            ConversationModel.customer_id == customer.id,
            ConversationModel.business_id == business.id,
            ConversationModel.status == 'active'
        ).first()

        if not conversation:
            conversation = ConversationModel(
                id=uuid.uuid4(),
                customer_id=customer.id,
                business_id=business.id,
                started_at=now_utc,
                last_message_at=now_utc,
                status='active'
            )
            db.add(conversation)
            db.flush() 
            logger.info(f"{log_prefix}: New Conversation ID {conversation.id} created for Customer {customer.id}.")
        else:
            conversation.last_message_at = now_utc
            logger.info(f"{log_prefix}: Using existing Conversation ID {conversation.id}.")

        inbound_message_record = Message(
            conversation_id=conversation.id,
            business_id=business.id,
            customer_id=customer.id,
            content=body_raw,
            message_type='inbound',
            status='received', 
            sent_at=now_utc, 
            message_metadata={'twilio_sid': message_sid_from_twilio, 'source': 'customer_reply'}
        )
        db.add(inbound_message_record)
        db.flush() 

        engagement = Engagement(
            customer_id=customer.id,
            business_id=business.id,
            message_id=inbound_message_record.id, 
            response=body_raw, 
            ai_response=None,  # Initialize, will be set by AI or if auto-reply happens
            status="pending_review", # Default, might change if auto-reply sent
            created_at=now_utc 
        )
        db.add(engagement) # Add to session early; ID will be assigned on flush/commit
        # It's good practice to flush here if you need engagement.id immediately, but commit will also do it.
        # db.flush() # If you need engagement.id for some reason before commit.

        logger.info(f"{log_prefix}: Customer message logged. Message ID: {inbound_message_record.id}, Engagement (pending ID or ID if flushed): {engagement.id if engagement.id else 'N/A'}")

        ai_service = AIService(db)
        ai_generated_response_data = None # To store the dict from AI service
        try:
            ai_generated_response_data = await ai_service.generate_sms_response( 
                message=body_raw, 
                business_id=business.id,
                customer_id=customer.id
            )
            
            # --- FIX for KeyError and TypeError (Issue 1 & 2 from previous step) ---
            ai_response_text_for_db = ai_generated_response_data.get('text', '') 
            engagement.ai_response = ai_response_text_for_db # Store only text in DB model
            # --- End FIX ---

            logger.info(f"{log_prefix}: AI response data received: {ai_generated_response_data}") # Log the whole dict
            logger.info(f"{log_prefix}: AI draft text for DB: '{ai_response_text_for_db[:50]}...'")

        except Exception as ai_err:
            logger.error(f"{log_prefix}: AI response generation failed: {ai_err}", exc_info=True)
            # engagement.ai_response remains None

        # --- START: Logic for Auto-Reply Based on FAQ ---
        if ai_generated_response_data and ai_generated_response_data.get("ai_can_reply_directly"):
            logger.info(f"{log_prefix}: AI determined it can reply directly as an FAQ answer.")
            faq_reply_text = ai_generated_response_data.get("text") # This should be the same as ai_response_text_for_db
            if faq_reply_text:
                try:
                    logger.info(f"{log_prefix}: Attempting to send FAQ auto-reply to {customer.phone}: '{faq_reply_text[:50]}...'")
                    # Use the main twilio_service instance
                    await twilio_service.send_sms(
                        to=customer.phone,
                        message=faq_reply_text,
                        business=business # Pass the full business object
                    )
                    engagement.status = "auto_replied_faq" 
                    engagement.sent_at = datetime.now(pytz.UTC) 
                    logger.info(f"{log_prefix}: FAQ auto-reply sent successfully. Engagement status set to 'auto_replied_faq'.")
                except Exception as auto_reply_send_err:
                    logger.error(f"{log_prefix}: Failed to send FAQ auto-reply: {auto_reply_send_err}", exc_info=True)
                    # If auto-reply fails, engagement status remains 'pending_review', owner will be notified.
            else:
                logger.warning(f"{log_prefix}: AI indicated direct reply for FAQ, but no text was generated.")
        # --- END: Logic for Auto-Reply Based on FAQ ---

        should_notify_owner = True
        if engagement.status == "auto_replied_faq":
            # Set to False if you DON'T want to notify the owner after a successful auto-reply
            # should_notify_owner = False
            pass 

        if should_notify_owner and business.notify_owner_on_reply_with_link and business.business_phone_number and business.slug:
            logger.info(f"{log_prefix}: Owner notification (Flow A) being prepared for Business {business.id}.")
            try:
                deep_link_url = f"{settings.FRONTEND_APP_URL}/profile/{business.slug}/inbox?conversationId={str(conversation.id)}"
                
                ai_draft_preview = ""
                # engagement.ai_response now correctly holds the string text from AI
                if engagement.ai_response and engagement.status != "auto_replied_faq": 
                    ai_draft_preview = f"\nAI Draft: \"{engagement.ai_response[:40]}{'...' if len(engagement.ai_response) > 40 else ''}\""

                notification_sms_body = (
                    f"AI Nudge: New SMS from {customer.customer_name}.\n"
                    f"\"{body_raw[:70]}{'...' if len(body_raw) > 70 else ''}\""
                    f"{ai_draft_preview}\n" 
                    f"Reply in app: {deep_link_url}"
                )
                
                logger.info(f"{log_prefix}: Sending owner notification to {business.business_phone_number} for Customer {customer.id}. Link: {deep_link_url}")
                await twilio_service.send_sms(
                    to=business.business_phone_number,
                    message=notification_sms_body,
                    business=business
                )
                logger.info(f"{log_prefix}: Owner SMS notification sent successfully to {business.business_phone_number}.")

            except Exception as notify_err:
                logger.error(f"{log_prefix}: Failed to send owner notification SMS for Business {business.id}: {notify_err}", exc_info=True)
        else:
            if engagement.status != "auto_replied_faq":
                logger.info(f"{log_prefix}: Owner notification (Flow A) SKIPPED for Business {business.id}. "
                            f"ShouldNotify: {should_notify_owner}, "
                            f"ConfigEnabled: {business.notify_owner_on_reply_with_link}, "
                            f"Phone: {'Set' if business.business_phone_number else 'Not Set'}, "
                            f"Slug: {'Set' if business.slug else 'Not Set'}")

        try:
            db.commit()
            logger.info(f"{log_prefix}: Database changes committed for inbound message and engagement.")
        except Exception as db_commit_err:
            db.rollback()
            logger.error(f"{log_prefix}: Final DB commit failed: {db_commit_err}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save message interaction.")

        return PlainTextResponse("SMS Received", status_code=status.HTTP_200_OK)

    except HTTPException as http_exc: 
        logger.error(f"HTTPException in webhook: {http_exc.detail}", exc_info=True)
        db.rollback() 
        raise http_exc
    except Exception as e:
        current_form_data_str = str(dict(form_data))[:500]
        logger.error(f"UNHANDLED EXCEPTION in webhook processing. SID: {message_sid_from_twilio}, From: {from_number_raw}, To: {to_number_raw}, Form Data (partial): {current_form_data_str}. Error: {e}", exc_info=True)
        logger.error(traceback.format_exc())
        db.rollback() 
        return PlainTextResponse("Internal Server Error processing webhook", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        logger.info(f"=== Twilio Webhook: END /inbound processing for SID:{message_sid_from_twilio} ===")