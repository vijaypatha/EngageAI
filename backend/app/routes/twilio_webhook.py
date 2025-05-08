# backend/app/routes/twilio_webhook.py

from datetime import datetime, timezone # Ensure timezone is imported if used directly
import logging
from typing import Dict, Optional # Removed unused TypeVar
import traceback

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessProfile, Customer, Engagement, ConsentLog
from app.services.ai_service import AIService
from app.services.consent_service import ConsentService
from app.config import settings

# Import the shared normalize_phone_number function
from app.schemas import normalize_phone_number # Assuming this is the correct location
import re # Ensure re is imported as normalize_phone_number uses it

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter()

@router.post("/inbound", response_class=PlainTextResponse)
async def receive_sms(
    request: Request,
    db: Session = Depends(get_db)
) -> PlainTextResponse:
    """
    Handle incoming SMS messages from Twilio webhook.
    Processes consent keywords first, then handles regular messages.
    """
    message_sid = "N/A" # Default SID for logging if parsing fails
    from_number_raw = "N/A"
    to_number_raw = "N/A" # For logging raw 'To' number
    logger.info("=== Twilio Webhook: START /inbound processing ===") # START marker
    try:
        form = await request.form()
        from_number_raw = form.get("From", "")
        to_number_raw = form.get("To", "") # Get raw 'To' number
        
        try:
            # The first argument 'cls' is not used by normalize_phone_number when called directly
            from_number = normalize_phone_number(None, from_number_raw)
        except ValueError as e:
            logger.error(f"Invalid 'From' phone number format from Twilio: '{from_number_raw}'. Error: {e}")
            return PlainTextResponse(f"Invalid 'From' number format received: {from_number_raw}", status_code=200)

        try:
            to_number = normalize_phone_number(None, to_number_raw)
        except ValueError as e:
            logger.error(f"Invalid 'To' phone number format from Twilio: '{to_number_raw}'. Error: {e}")
            return PlainTextResponse(f"Invalid 'To' number format received: {to_number_raw}", status_code=200)

        body_raw = form.get("Body", "")
        body = body_raw.strip().lower() # Use lower case body for processing
        message_sid = form.get("MessageSid", "")
        
        logger.info(f"Webhook Raw Payload: From={from_number_raw}, To={to_number_raw}, Body='{body_raw}', SID={message_sid}")
        logger.info(f"Webhook Normalized Data: From={from_number}, To={to_number}, Body='{body}', SID={message_sid}")

        if not all([from_number, to_number, body_raw.strip()]):
            logger.error(f"Webhook missing required parameters. From: {from_number}, To: {to_number}, Body Raw: '{body_raw}', SID: {message_sid}")
            return PlainTextResponse("Missing parameters", status_code=200)

        # --- Consent Processing Logic ---
        pending_log = db.query(ConsentLog).filter(
            ConsentLog.phone_number == from_number,
            ConsentLog.status.in_(["pending_confirmation", "pending"])
        ).order_by(ConsentLog.sent_at.desc()).first()

        if pending_log:
            logger.info(f"Found PENDING consent log (ID: {pending_log.id}, Status: {pending_log.status}) for {from_number}. Will attempt to process response '{body}'.")
        else:
            logger.info(f"NO PENDING consent log (with status 'pending' or 'pending_confirmation') found for {from_number} for message '{body}'. ConsentService might not update based on this message if it's a 'yes'/'no', unless it's a global 'stop'.")
            
        consent_service = ConsentService(db)
        logger.info(f"Attempting to process '{body}' as consent response via ConsentService for {from_number} (SID: {message_sid})")
        consent_response_from_service = await consent_service.process_sms_response(
            phone_number=from_number,
            response=body
        )

        if consent_response_from_service:
            logger.info(f"Consent response processed by ConsentService for {from_number} (SID: {message_sid}). Returning service response to Twilio.")
            return consent_response_from_service 
        else:
             logger.info(f"Message '{body}' from {from_number} (SID: {message_sid}) not processed as a standard consent keyword/update by ConsentService or no relevant pending log was found/updated by it.")

        # --- Regular Message Handling (Only if not handled as consent) ---
        logger.info(f"Proceeding to handle message from {from_number} to {to_number} (SID: {message_sid}) as regular inbound.")

        # 1. Identify the BusinessProfile using the 'to_number' (the Twilio number that received the SMS)
        # Ensure BusinessProfile.twilio_number is stored in a consistent, normalized E.164 format.
        business = db.query(BusinessProfile).filter(BusinessProfile.twilio_number == to_number).first()
        if not business:
            logger.error(f"No business found associated with Twilio number {to_number} (SID: {message_sid}). Cannot route message.")
            return PlainTextResponse("Receiving number not associated with a business", status_code=200)
        logger.info(f"Message to {to_number} routed to Business (ID: {business.id}, Name: {business.business_name}). SID: {message_sid}")

        # 2. Find the Customer based on their phone number (from_number) AND the identified business_id
        customer = db.query(Customer).filter(
            Customer.phone == from_number,
            Customer.business_id == business.id  # Ensure customer belongs to this business
        ).first()

        if not customer:
            logger.warning(f"No customer record found with phone {from_number} for Business ID {business.id} (SID: {message_sid}).")
            # Optional: Logic to create a new customer if they message a business they aren't associated with yet.
            # For now, we'll assume the customer must exist for this business.
            return PlainTextResponse("Customer not found for this business", status_code=200)
        logger.info(f"Found Customer (ID: {customer.id}, Name: {customer.customer_name}) for Business ID {business.id} from {from_number}. SID: {message_sid}")

        # 3. Check customer opt-in status
        if not customer.opted_in:
             logger.warning(f"Ignoring message '{body}' from non-opted-in Customer {customer.id} ({from_number}) for Business {business.id}. SID: {message_sid}")
             return PlainTextResponse("Customer not opted-in", status_code=200)
        
        logger.info(f"Customer {customer.id} ({from_number}) is opted-in for Business {business.id}. Processing message: '{body}'. SID: {message_sid}")
        # The 'business' variable is now correctly identified and associated with the 'to_number'.

        # --- Generate AI response and save Engagement ---
        logger.info(f"Generating AI response for customer {customer.id}, business {business.id} (SID: {message_sid})")
        ai_service = AIService(db)
        try:
            ai_response_text = await ai_service.generate_sms_response( 
                message=body_raw.strip(), 
                business_id=business.id, # Use the correctly identified business
                customer_id=customer.id
            )
            logger.info(f"AI Response generated for SID {message_sid}: {ai_response_text}")
        except Exception as e:
            logger.error(f"AI generation failed for SID {message_sid}: {e}", exc_info=True)
            return PlainTextResponse("Received (AI generation failed)", status_code=200)

        logger.info(f"Saving engagement for customer {customer.id}, business {business.id} (SID: {message_sid})")
        try:
            engagement = Engagement(
                customer_id=customer.id,
                business_id=business.id, # Use the correctly identified business
                response=body_raw.strip(), 
                ai_response=ai_response_text, 
                status="pending_review", 
                sent_at=None 
            )
            db.add(engagement)
            db.commit()
            logger.info(f"Engagement saved (ID: {engagement.id}) for customer {customer.id}, business {business.id} (SID: {message_sid})")
        except Exception as e:
            logger.error(f"DB commit failed saving engagement for SID {message_sid}: {e}", exc_info=True)
            db.rollback()
            return PlainTextResponse("Received (DB save failed)", status_code=200)

        # Consider what to respond to Twilio. An empty 200 OK is fine.
        # Or a generic "Got your message!" if you want to send a TwiML response.
        # For API-only processing, an empty 200 is standard.
        return PlainTextResponse("Got your message! We'll get back to you shortly.", status_code=200)


    except Exception as e:
        logger.error(f"Unhandled exception in webhook processing for SID {message_sid} from {from_number_raw}: {str(e)}", exc_info=True)
        logger.error(traceback.format_exc())
        return PlainTextResponse("Internal Server Error during webhook processing", status_code=500)
    finally:
        logger.info(f"=== Twilio Webhook: END /inbound processing for SID {message_sid} ===")