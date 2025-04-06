# app/routes/twilio_webhook.py
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Customer, Engagement, BusinessProfile
from app.services.sms_reply_generator import generate_ai_response
from fastapi.responses import PlainTextResponse
import os
from twilio.rest import Client

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
    # Log incoming content type (e.g. application/x-www-form-urlencoded)
    content_type = request.headers.get("content-type")
    print("📥 Content-Type:", content_type)

    # Parse form data from Twilio webhook
    form = await request.form()
    from_number = normalize_phone(form.get("From") or "")
    to_number = normalize_phone(form.get("To") or "")
    body = form.get("Body")

    # Log raw incoming message info
    print(f"🔍 Incoming SMS: From={from_number}, To={to_number}, Body={body}")

    # -------------------- STEP 1: Identify Business by To Number --------------------
    business = db.query(BusinessProfile).filter(BusinessProfile.twilio_number == to_number).first()
    if not business:
        print(f"❌ No business matches Twilio number {to_number}")
        return PlainTextResponse("Business not found", status_code=404)

    # -------------------- STEP 2: Match Customer by From Number + Business --------------------
    customer = db.query(Customer).filter(
        Customer.phone == from_number,
        Customer.business_id == business.id
    ).first()
    if not customer:
        print(f"❌ Customer {from_number} not found for business {business.id}")
        return PlainTextResponse("Customer not found", status_code=404)

    # -------------------- STEP 3: Generate AI Drafted Reply --------------------
    ai_response = generate_ai_response(body, business=business, customer=customer)
    print(f"🤖 AI Response: {ai_response}")

    # -------------------- STEP 4: Save Engagement Record --------------------
    engagement = Engagement(
        customer_id=customer.id,
        response=body,
        ai_response=ai_response  # Stored for manual review
    )
    db.add(engagement)
    db.commit()
    print(f"✅ Engagement saved with AI response for customer {customer.id} (Engagement ID: {engagement.id})")

    # -------------------- STEP 5: Manual Approval Flow --------------------
    # We are NOT sending this SMS now — it will be reviewed and sent manually via the dashboard
    print("✅ AI reply stored. Waiting for manual approval before sending.")
    return PlainTextResponse("Received", status_code=200)


    
    # ### --------------------- INSERT BLOCK 2 HERE --------------------- ###
    # # Send the AI response back via Twilio (only if we have one)
    # if client and twilio_phone_number and ai_response:
    #     try:
    #         message = client.messages.create(
    #             to=from_number,
    #             from_=twilio_phone_number,
    #             body=ai_response,
    #         )
    #         print(f"📤 Sent AI response to {from_number}. Message SID: {message.sid}")
    #         return PlainTextResponse("Received and Replied", status_code=200)
    #     except Exception as e:
    #         print(f"❌ Error sending Twilio message: {e}")
    #         return PlainTextResponse("Received, but error sending reply", status_code=500)
    # else:
    #     print("⚠️ Could not send AI reply (either AI failed or Twilio not configured). Acknowledging receipt.")
    #     return PlainTextResponse("Received", status_code=200) # Fallback to just "Received"


    # ### --------------------- END OF BLOCK 2 --------------------- ###

    # return PlainTextResponse("Received", status_code=200)



# from fastapi import APIRouter, Request, Depends, status
# from sqlalchemy.orm import Session
# from app.database import get_db
# from app.models import Customer, Engagement
# from fastapi.responses import PlainTextResponse

# router = APIRouter()

# print("✅ Twilio webhook router loaded")

# @router.post("/inbound", response_class=PlainTextResponse)
# async def receive_sms(request: Request, db: Session = Depends(get_db)):
#     try:
#         content_type = request.headers.get("content-type")
#         print("📥 Content-Type:", content_type)

#         form = await request.form()
#         from_number = form.get("From")
#         body = form.get("Body")

#         print("🔍 From =", from_number)
#         print("📝 Body =", body)

#         if not from_number or not body:
#             return PlainTextResponse("Missing data", status_code=400)

#         normalized = "+" + from_number.replace(" ", "").lstrip("+")
#         print("🔧 Normalized =", normalized)

#         customer = db.query(Customer).filter(Customer.phone == normalized).first()
#         if not customer:
#             return PlainTextResponse("Customer not found", status_code=404)

#         engagement = Engagement(customer_id=customer.id, response=body)
#         db.add(engagement)
#         db.commit()

#         return PlainTextResponse("Received", status_code=200)
    
#     except Exception as e:
#         print("❌ Exception occurred:", str(e))
#         return PlainTextResponse("Server error", status_code=500)
