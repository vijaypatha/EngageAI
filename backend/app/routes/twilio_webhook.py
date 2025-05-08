# backend/app/routes/twilio_webhook.py

from datetime import datetime, timezone # Ensure timezone is imported if used directly
import logging
from typing import Dict, Optional
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
from app.schemas import normalize_phone_number # << IMPORTED HERE
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
        
        # Use the imported normalize_phone_number function from app.schemas
        try:
            # The first argument 'cls' is not used by normalize_phone_number when called directly
            from_number = normalize_phone_number(None, from_number_raw)
        except ValueError as e:
            logger.error(f"Invalid 'From' phone number format from Twilio: '{from_number_raw}'. Error: {e}")
            # Twilio should send valid E.164. If not, it's problematic.
            # Return 200 to Twilio to acknowledge receipt and prevent retries, but log it as critical.
            return PlainTextResponse(f"Invalid 'From' number format received: {from_number_raw}", status_code=200)

        try:
            to_number = normalize_phone_number(None, to_number_raw)
        except ValueError as e:
            logger.error(f"Invalid 'To' phone number format from Twilio: '{to_number_raw}'. Error: {e}")
            return PlainTextResponse(f"Invalid 'To' number format received: {to_number_raw}", status_code=200)

        body_raw = form.get("Body", "")
        body = body_raw.strip().lower() # Use lower case body for processing
        message_sid = form.get("MessageSid", "") # Get the Message SID
        
        logger.info(f"Webhook Raw Payload: From={from_number_raw}, To={to_number_raw}, Body='{body_raw}', SID={message_sid}")
        logger.info(f"Webhook Normalized Data: From={from_number}, To={to_number}, Body='{body}', SID={message_sid}")

        # Ensure body_raw is not just whitespace before considering it missing.
        if not all([from_number, to_number, body_raw.strip()]):
            logger.error(f"Webhook missing required parameters. From: {from_number}, To: {to_number}, Body Raw: '{body_raw}', SID: {message_sid}")
            # Still return 200 to Twilio to prevent retries for bad requests
            return PlainTextResponse("Missing parameters", status_code=200)

        # --- Consent Processing Logic ---
        # Check for existing pending consent log for this customer phone number
        pending_log = db.query(ConsentLog).filter(
            ConsentLog.phone_number == from_number, # Use normalized from_number
            ConsentLog.status.in_(["pending_confirmation", "pending"]) # Check for multiple pending states
        ).order_by(ConsentLog.sent_at.desc()).first()

        if pending_log:
            logger.info(f"Found PENDING consent log (ID: {pending_log.id}, Status: {pending_log.status}) for {from_number}. Will attempt to process response '{body}'.")
        else:
            logger.info(f"NO PENDING consent log (with status 'pending' or 'pending_confirmation') found for {from_number} for message '{body}'. ConsentService might not update based on this message if it's a 'yes'/'no', unless it's a global 'stop'.")
            
        consent_service = ConsentService(db)
        logger.info(f"Attempting to process '{body}' as consent response via ConsentService for {from_number} (SID: {message_sid})")
        consent_response_from_service = await consent_service.process_sms_response(
            phone_number=from_number, # Pass normalized from_number
            response=body # Pass the lowercased body
        )

        if consent_response_from_service:
            logger.info(f"Consent response processed by ConsentService for {from_number} (SID: {message_sid}). Returning service response to Twilio.")
            return consent_response_from_service 
        else:
             logger.info(f"Message '{body}' from {from_number} (SID: {message_sid}) not processed as a standard consent keyword/update by ConsentService or no relevant pending log was found/updated by it.")

        # --- Regular Message Handling (Only if not handled as consent) ---
        logger.info(f"Proceeding to handle message from {from_number} (SID: {message_sid}) as regular inbound.")
        
        # Find customer by THEIR phone number (normalized)
        # Assuming Customer.phone is stored in a normalized E.164 format due to schema validators
        customer = db.query(Customer).filter(Customer.phone == from_number).first()
        if not customer:
            logger.warning(f"No customer record found for {from_number} (SID: {message_sid}). Cannot process regular message.")
            return PlainTextResponse("Customer not found", status_code=200) 
        logger.info(f"Found customer (ID: {customer.id}) associated with {from_number}.")

        if not customer.opted_in:
             logger.warning(f"Ignoring message '{body}' from non-opted-in customer {customer.id} ({from_number}) (SID: {message_sid}).")
             return PlainTextResponse("Customer not opted-in", status_code=200) 
        
        logger.info(f"Customer {customer.id} ({from_number}) is opted-in. Processing message: '{body}' (SID: {message_sid})")
        
        business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
        if not business:
            logger.error(f"Business profile not found for customer {customer.id} (Business ID: {customer.business_id}) (SID: {message_sid}).")
            return PlainTextResponse("Internal Error: Business profile missing", status_code=500) 
        logger.info(f"Found business (ID: {business.id}, Name: {business.business_name}) for customer {customer.id}.")

        logger.info(f"Generating AI response for customer {customer.id}, business {business.id} (SID: {message_sid})")
        ai_service = AIService(db)
        try:
            ai_response_text = await ai_service.generate_sms_response( 
                message=body_raw.strip(), 
                business_id=business.id,
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
                business_id=business.id,
                response=body_raw.strip(), 
                ai_response=ai_response_text, 
                status="pending_review", 
                sent_at=None 
            )
            db.add(engagement)
            db.commit()
            logger.info(f"Engagement saved (ID: {engagement.id}) for customer {customer.id} (SID: {message_sid})")
        except Exception as e:
            logger.error(f"DB commit failed saving engagement for SID {message_sid}: {e}", exc_info=True)
            db.rollback()
            return PlainTextResponse("Received (DB save failed)", status_code=200)

        return PlainTextResponse("Got your message! We'll get back to you shortly.", status_code=200)

    except Exception as e:
        logger.error(f"Unhandled exception in webhook processing for SID {message_sid} from {from_number_raw}: {str(e)}", exc_info=True)
        logger.error(traceback.format_exc())
        return PlainTextResponse("Internal Server Error during webhook processing", status_code=500)
    finally:
        logger.info(f"=== Twilio Webhook: END /inbound processing for SID {message_sid} ===")