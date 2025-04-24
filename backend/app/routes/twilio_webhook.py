from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Customer, Engagement, BusinessProfile, ConsentLog
from app.services.sms_reply_generator import generate_ai_response
from app.services.optin_handler import handle_opt_in_out
from fastapi.responses import PlainTextResponse
import os
from twilio.rest import Client
from datetime import datetime, timezone
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# -------------------- Twilio Client Setup --------------------
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
default_twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER")
client = Client(account_sid, auth_token) if account_sid and auth_token else None

# Normalize phone number into +1XXXXXXXXXX format
def normalize_phone(number: str) -> str:
    return "+" + number.strip().replace(" ", "").lstrip("+")

def update_customer_consent(customer: Customer, status: str, db: Session):
    """Update customer consent status and log the change."""
    now = datetime.now(timezone.utc)
    
    # Update customer opted_in status
    if status == "opted_in":
        customer.opted_in = True
    elif status == "opted_out":
        customer.opted_in = False
    
    # Create consent log entry
    consent_log = ConsentLog(
        customer_id=customer.id,
        business_id=customer.business_id,
        status=status,
        method="sms",
        replied_at=now
    )
    
    db.add(consent_log)
    try:
        db.commit()
        logger.info(f"Updated consent status for customer {customer.id} to {status}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update consent status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update consent status")

# -------------------- Inbound SMS Webhook --------------------
@router.post("/inbound", response_class=PlainTextResponse)
async def receive_sms(request: Request, db: Session = Depends(get_db)):
    try:
        form = await request.form()
        from_number = normalize_phone(form.get("From", ""))
        to_number = normalize_phone(form.get("To", ""))
        body = form.get("Body", "").strip().lower()

        # -------------------- STEP 1: Validate Input --------------------
        if not from_number or not to_number or not body:
            logger.error("Missing required SMS webhook parameters")
            return PlainTextResponse("Missing parameters", status_code=400)

        # -------------------- STEP 2: Match Customer + Business --------------------
        customer = db.query(Customer).filter(Customer.phone == from_number).first()
        if not customer:
            logger.warning(f"No customer found for phone number {from_number}")
            return PlainTextResponse("Customer not found", status_code=404)

        business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
        if not business:
            logger.error(f"No business found for customer {customer.id}")
            return PlainTextResponse("Business not found", status_code=404)

        logger.info(f"📇 Matched customer: ID={customer.id}, phone={customer.phone}, opted_in={customer.opted_in}")

        # -------------------- STEP 3: Handle Consent --------------------
        consent_words = {
            "opted_in": ["yes", "start", "unstop", "subscribe", "opt in", "opt-in"],
            "opted_out": ["no", "stop", "unsubscribe", "opt out", "opt-out"]
        }
        
        # Check for consent-related keywords
        for status, keywords in consent_words.items():
            if any(keyword in body for keyword in keywords):
                update_customer_consent(customer, status, db)
                message = "You've successfully opted in to messages." if status == "opted_in" else "You've been unsubscribed from messages."
                return PlainTextResponse(message, status_code=200)

        # -------------------- STEP 4: Handle Regular Message --------------------
        if not customer.opted_in:
            logger.warning(f"Ignoring message from opted-out customer {customer.id}")
            return PlainTextResponse("Opted-out user. No response generated.", status_code=200)

        # Generate AI response
        logger.info("🧠 Proceeding to AI response generation...")
        ai_response = generate_ai_response(body, business=business, customer=customer)
        logger.info(f"🤖 AI Response: {ai_response}")

        # Save engagement record
        engagement = Engagement(
            customer_id=customer.id,
            response=body,
            ai_response=ai_response,
            status="pending_review",
            sent_at=datetime.now(timezone.utc)
        )
        db.add(engagement)
        db.commit()
        logger.info(f"✅ Engagement saved with AI response for customer {customer.id} (Engagement ID: {engagement.id})")

        return PlainTextResponse("Received", status_code=200)

    except Exception as e:
        logger.error(f"❌ Exception in webhook: {str(e)}")
        return PlainTextResponse("Internal Error", status_code=500)
