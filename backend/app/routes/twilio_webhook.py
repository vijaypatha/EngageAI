from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Customer, Engagement, BusinessProfile, ConsentLog
from app.services.sms_reply_generator import generate_ai_response
from app.services.optin_handler import handle_opt_in_out
from fastapi.responses import PlainTextResponse
import os
from twilio.rest import Client
from datetime import datetime

router = APIRouter()

# -------------------- Twilio Client Setup --------------------
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
default_twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER")
client = Client(account_sid, auth_token) if account_sid and auth_token else None

# Normalize phone number into +1XXXXXXXXXX format
def normalize_phone(number: str) -> str:
    return "+" + number.strip().replace(" ", "").lstrip("+")

# -------------------- Inbound SMS Webhook --------------------
@router.post("/inbound", response_class=PlainTextResponse)
async def receive_sms(request: Request, db: Session = Depends(get_db)):
    try:
        print("🚨 Twilio webhook received — starting /twilio/inbound processing")
        content_type = request.headers.get("content-type")
        print(f"📥 Incoming request content-type: {content_type}")

        raw = await request.body()
        print(f"📦 Raw body content: {raw.decode(errors='ignore')}")
        form = await request.form()
        from_number_raw = (form.get("From") or "").strip()
        to_number_raw = (form.get("To") or "").strip()
        from_number = normalize_phone(from_number_raw)
        to_number = normalize_phone(to_number_raw)
        body = form.get("Body")

        if not body:
            print("⚠️ No SMS body received.")
            return PlainTextResponse("No SMS body received", status_code=400)

        print(f"🔍 Incoming SMS: From={from_number}, To={to_number}, Body={body}")

        # -------------------- STEP 1: Identify Business by To Number --------------------
        business = db.query(BusinessProfile).filter(BusinessProfile.twilio_number == to_number).first()
        if not business:
            print(f"❌ No business matches Twilio number {to_number}")
            return PlainTextResponse("Business not found", status_code=404)

        # -------------------- STEP 2: Match Latest Customer by From Number + Business --------------------
        customer = db.query(Customer)\
            .filter(Customer.phone == from_number, Customer.business_id == business.id)\
            .order_by(Customer.id.desc())\
            .first()

        if not customer:
            print(f"❌ Customer {from_number} not found for business {business.id}")
            return PlainTextResponse("Customer not found", status_code=404)

        print(f"📇 Matched customer: ID={customer.id}, phone={customer.phone}, opted_in={customer.opted_in}")

        # -------------------- STEP 3: Normalize Body + Handle Consent --------------------
        response = handle_opt_in_out(body, customer, business, db)
        if response:
            return response

        # -------------------- STEP 4: Abort if user has opted out --------------------
        if customer.opted_in is False:
            print(f"🔒 Customer {customer.id} has opted out. Ignoring message.")
            return PlainTextResponse("Opted-out user. No response generated.", status_code=200)

        # -------------------- STEP 5: Generate AI Drafted Reply --------------------
        print("🧠 Proceeding to AI response generation...")
        ai_response = generate_ai_response(body, business=business, customer=customer)
        print(f"🤖 AI Response: {ai_response}")

        # -------------------- STEP 6: Save Engagement Record --------------------
        engagement = Engagement(
            customer_id=customer.id,
            response=body,
            ai_response=ai_response,  # Stored for manual review
            status="pending_review"
        )
        db.add(engagement)
        db.commit()
        print(f"✅ Engagement saved with AI response for customer {customer.id} (Engagement ID: {engagement.id})")

        # -------------------- STEP 7: Manual Approval Flow --------------------
        print("✅ AI reply stored. Waiting for manual approval before sending.")
        return PlainTextResponse("Received", status_code=200)

    except Exception as e:
        print(f"❌ Exception in webhook: {str(e)}")
        return PlainTextResponse("Internal Error", status_code=500)
