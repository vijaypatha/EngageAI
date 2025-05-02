# Handles incoming SMS messages from customers and manages automated responses
# Business owners receive customer messages and can track engagement through this webhook
from datetime import datetime, timezone
import logging
from typing import Dict, Optional
import traceback

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessProfile, Customer, Engagement
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
    
    Args:
        number: Phone number to normalize
        
    Returns:
        Normalized phone number in E.164 format
    """
    return "+" + number.strip().replace(" ", "").lstrip("+")

@router.post("/inbound", response_class=PlainTextResponse)
async def receive_sms(
    request: Request,
    db: Session = Depends(get_db)
) -> PlainTextResponse:
    """
    Handle incoming SMS messages from Twilio webhook.
    
    Args:
        request: FastAPI request object containing form data
        db: Database session
        
    Returns:
        PlainTextResponse with appropriate status message
        
    Raises:
        HTTPException: For various error conditions
    """
    try:
        logger.info("=== Twilio Webhook: Incoming SMS received ===")
        form = await request.form()
        from_number = normalize_phone(form.get("From", ""))
        to_number = normalize_phone(form.get("To", ""))
        body = form.get("Body", "").strip()

        logger.info(f"Webhook payload: From={from_number}, To={to_number}, Body='{body}'")

        if not all([from_number, to_number, body]):
            logger.error("Missing required SMS webhook parameters")
            return PlainTextResponse("Missing parameters", status_code=400)

        # Find customer and business
        customer = db.query(Customer).filter(Customer.phone == from_number).first()
        if not customer:
            logger.warning(f"No customer found for phone number {from_number}")
            return PlainTextResponse("Customer not found", status_code=404)
        logger.info(f"Matched customer: ID={customer.id}, phone={customer.phone}, opted_in={customer.opted_in}")

        business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
        if not business:
            logger.error(f"No business found for customer {customer.id}")
            return PlainTextResponse("Business not found", status_code=404)
        logger.info(f"Matched business: ID={business.id}, name={business.business_name}")

        # Initialize services
        consent_service = ConsentService(db)
        ai_service = AIService(db)

        # Handle consent keywords
        consent_words: Dict[str, list[str]] = {
            "opted_in": ["yes", "start", "unstop", "subscribe", "opt in", "opt-in"],
            "opted_out": ["no", "stop", "unsubscribe", "opt out", "opt-out"]
        }
        for status, keywords in consent_words.items():
            if any(keyword in body.lower() for keyword in keywords):
                logger.info(f"Consent keyword detected: {status}")
                await consent_service.update_consent_status(
                    customer_id=customer.id,
                    status=status,
                    method="sms"
                )
                message = (
                    "You've successfully opted in to messages."
                    if status == "opted_in"
                    else "You've been unsubscribed from messages."
                )
                logger.info(f"Consent status updated for customer {customer.id}: {status}")
                return PlainTextResponse(message, status_code=200)

        # Check consent status before proceeding
        has_consent = await consent_service.check_consent(customer.id)
        logger.info(f"Consent check for customer {customer.id}: {has_consent}")
        if not has_consent:
            logger.warning(f"Ignoring message from opted-out customer {customer.id}")
            return PlainTextResponse("Opted-out user. No response generated.", status_code=200)

        # Generate AI response
        logger.info("Proceeding to AI response generation...")
        ai_response = await ai_service.generate_sms_response(
            message=body,
            business_id=business.id,
            customer_id=customer.id
        )
        logger.info(f"AI Response generated: {ai_response}")

        # Save engagement
        logger.info("Saving engagement to database...")
        engagement = Engagement(
            customer_id=customer.id,
            business_id=business.id,
            response=body,
            ai_response=ai_response,
            status="pending_review",
            sent_at=datetime.now(timezone.utc)
        )
        db.add(engagement)
        db.commit()
        logger.info(f"Engagement saved with ID={engagement.id} for customer {customer.id}")

        return PlainTextResponse("Received", status_code=200)

    except Exception as e:
        logger.error(f"Exception in webhook: {str(e)}", exc_info=True)
        logger.error(traceback.format_exc())
        return PlainTextResponse("Internal Error", status_code=500)
