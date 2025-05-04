# Handles incoming SMS messages from customers and manages automated responses
# Business owners receive customer messages and can track engagement through this webhook
# backend/app/routes/twilio_webhook.py

# Handles incoming SMS messages from customers and manages automated responses
# Business owners receive customer messages and can track engagement through this webhook
from datetime import datetime, timezone
import logging
from typing import Dict, Optional
import traceback # Import traceback

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
# Import models needed here
from app.models import BusinessProfile, Customer, Engagement, ConsentLog 
# Import services needed here
from app.services.ai_service import AIService 
from app.services.consent_service import ConsentService 
from app.config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter()

def normalize_phone(number: str) -> str:
    """
    Normalize phone number to E.164 format (+1XXXXXXXXXX).
    """
    if not number: # Handle empty string case
        return ""
    # Basic cleaning, ensure '+' prefix
    cleaned = "".join(filter(str.isdigit, number))
    if len(cleaned) == 10:
        return f"+1{cleaned}"
    if len(cleaned) == 11 and cleaned.startswith('1'):
        return f"+{cleaned}"
    if number.startswith('+') and len(cleaned) > 10: # Assume already E.164-like if starts with +
         return "+" + "".join(filter(str.isdigit, number[1:])) # Ensure only digits after +
    # Fallback or raise error if format is unexpected
    logger.warning(f"Could not normalize phone number reliably: {number}")
    return "+" + cleaned # Best effort


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
    logger.info("=== Twilio Webhook: START /inbound processing ===") # START marker
    try:
        form = await request.form()
        from_number_raw = form.get("From", "")
        from_number = normalize_phone(from_number_raw) # Customer's number
        to_number = normalize_phone(form.get("To", ""))     # Your Twilio number
        body_raw = form.get("Body", "")
        body = body_raw.strip().lower() # Use lower case body for processing
        message_sid = form.get("MessageSid", "") # Get the Message SID
        
        logger.info(f"Webhook Raw Payload: From={from_number_raw}, To={form.get('To')}, Body='{body_raw}', SID={message_sid}")
        logger.info(f"Webhook Normalized Data: From={from_number}, To={to_number}, Body='{body}', SID={message_sid}")

        if not all([from_number, to_number, body]):
            logger.error(f"Webhook missing required parameters. SID: {message_sid}")
            # Still return 200 to Twilio to prevent retries for bad requests
            return PlainTextResponse("Missing parameters", status_code=200) 

        # --- Consent Processing Logic ---
        
        # Check for existing pending consent log for this customer phone number
        # We do this early for logging purposes
        pending_log = db.query(ConsentLog).filter(
            ConsentLog.phone_number == from_number,
            ConsentLog.status == "pending" # Specifically look for 'pending'
        ).order_by(ConsentLog.sent_at.desc()).first()

        if pending_log:
            logger.info(f"Found PENDING consent log (ID: {pending_log.id}) for {from_number}. Will attempt to process response '{body}'.")
        else:
            # This log is important if 'Yes' arrives but isn't processed
            logger.warning(f"NO PENDING consent log found for {from_number}. ConsentService.process_sms_response will not update status based on this message ('{body}').")
            
        # Instantiate ConsentService
        consent_service = ConsentService(db)
        
        # Attempt to process the incoming message as a potential consent response ('yes', 'no', 'stop', etc.)
        logger.info(f"Attempting to process '{body}' as consent response via ConsentService for {from_number} (SID: {message_sid})")
        consent_response_from_service = await consent_service.process_sms_response(
            phone_number=from_number, 
            response=body # Pass the lowercased body
        )

        if consent_response_from_service:
            # If process_sms_response handled it (e.g., was 'yes'/'no'/'stop') AND found/updated a pending log
            logger.info(f"Consent response processed by ConsentService for {from_number} (SID: {message_sid}). Returning service response to Twilio.")
            # The service returns a PlainTextResponse object (e.g., "Opt-in confirmed.") to send back to Twilio
            return consent_response_from_service 
        else:
            # If it wasn't a standard consent keyword OR if no pending log was found by the service
             logger.info(f"Message '{body}' from {from_number} (SID: {message_sid}) not processed as a standard consent keyword/update by ConsentService.")
             # Proceed to handle as a regular message ONLY IF customer is already opted in

        # --- Regular Message Handling (Only if not handled as consent) ---
        
        logger.info(f"Proceeding to handle message from {from_number} (SID: {message_sid}) as regular inbound.")
        
        # Find customer by THEIR phone number
        customer = db.query(Customer).filter(Customer.phone == from_number).first()
        if not customer:
            logger.warning(f"No customer record found for {from_number} (SID: {message_sid}). Cannot process regular message.")
            # Acknowledge receipt to Twilio but take no further action
            return PlainTextResponse("Customer not found", status_code=200) 
        logger.info(f"Found customer (ID: {customer.id}) associated with {from_number}.")

        # Check if customer is actually opted-in before processing regular messages
        # Use the direct check on the Customer model now, assuming process_sms_response updated it if needed
        if not customer.opted_in:
             logger.warning(f"Ignoring message '{body}' from non-opted-in customer {customer.id} (SID: {message_sid}).")
             # Acknowledge receipt to Twilio but take no further action
             return PlainTextResponse("Customer not opted-in", status_code=200) 
        
        logger.info(f"Customer {customer.id} is opted-in. Processing message: '{body}' (SID: {message_sid})")
        
        # Find associated business
        business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
        if not business:
            logger.error(f"Business profile not found for customer {customer.id} (Business ID: {customer.business_id}) (SID: {message_sid}).")
            # This is an internal data integrity issue
            return PlainTextResponse("Internal Error: Business profile missing", status_code=500) 
        logger.info(f"Found business (ID: {business.id}, Name: {business.business_name}) for customer {customer.id}.")


        # --- Generate AI response and save Engagement (Your existing logic for regular messages) ---
        logger.info(f"Generating AI response for customer {customer.id}, business {business.id} (SID: {message_sid})")
        ai_service = AIService(db)
        try:
            # Ensure body here is the ORIGINAL case if AI needs it, or use lowercased 'body' if preferred
            ai_response = await ai_service.generate_sms_response( 
                message=body_raw.strip(), # Use original case body for AI?
                business_id=business.id,
                customer_id=customer.id
            )
            logger.info(f"AI Response generated for SID {message_sid}: {ai_response}")
        except Exception as e:
            logger.error(f"AI generation failed for SID {message_sid}: {e}", exc_info=True)
            # Decide how to handle AI failure - just acknowledge receipt?
            return PlainTextResponse("Received (AI generation failed)", status_code=200)

        logger.info(f"Saving engagement for customer {customer.id}, business {business.id} (SID: {message_sid})")
        try:
            engagement = Engagement(
                customer_id=customer.id,
                business_id=business.id,
                response=body_raw.strip(), # Store original case message from customer
                ai_response=ai_response, # Store generated AI response
                status="pending_review", # Mark for review
                sent_at=None 
            )
            db.add(engagement)
            db.commit()
            logger.info(f"Engagement saved (ID: {engagement.id}) for customer {customer.id} (SID: {message_sid})")
        except Exception as e:
            logger.error(f"DB commit failed saving engagement for SID {message_sid}: {e}", exc_info=True)
            db.rollback()
            # Decide how to handle DB failure - just acknowledge receipt?
            return PlainTextResponse("Received (DB save failed)", status_code=200)

        # Acknowledge receipt to Twilio after successful processing
        return PlainTextResponse("Received", status_code=200)

    except Exception as e:
        # Catch-all for any unexpected errors during the process
        logger.error(f"Unhandled exception in webhook processing for SID {message_sid} from {from_number_raw}: {str(e)}", exc_info=True)
        logger.error(traceback.format_exc())
        # Return 500; Twilio might retry based on its settings
        return PlainTextResponse("Internal Server Error during webhook processing", status_code=500)
    finally:
        logger.info(f"=== Twilio Webhook: END /inbound processing for SID {message_sid} ===") # END marker
