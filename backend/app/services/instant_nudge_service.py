# instant_nudge_service.py
# Provides AI-powered SMS generation and handling logic for the Instant Nudge feature.
# Includes generation of personalized messages and logic to send or schedule them.

from typing import List, Dict
from datetime import datetime
import openai
import os
import pytz

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import BusinessProfile, BusinessOwnerStyle, ScheduledSMS, Engagement, Customer
from app.services.twilio_sms_service import send_sms_via_twilio
from app.utils import parse_sms_timing
from app.celery_tasks import schedule_sms_task


# Helper: Call OpenAI to generate short SMS message
def call_openai_completion(prompt: str) -> str:
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=120,
        messages=[
            {"role": "system", "content": "You write short, helpful SMS messages."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()


# Generate a single AI message with customer name placeholder
async def generate_instant_nudge(topic: str, business_id: int) -> dict:
    db: Session = SessionLocal()

    # Lookup business profile
    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        print(f"❌ BusinessProfile not found for business_id={business_id}")
        raise Exception("Business not found")

    # Lookup tone/style if saved by business owner
    style = db.query(BusinessOwnerStyle).filter(BusinessOwnerStyle.business_id == business_id).first()
    tone_instructions = style.response if style else "friendly and helpful tone"

    # Build prompt to feed OpenAI
    prompt = (
        f"You're {business.representative_name} from {business.business_name}. "
        f"Write a short, friendly SMS message to a customer about: '{topic}'. "
        f"Use a {tone_instructions}. Include '{{customer_name}}' where the name should go."
    )

    print(f"🧠 Generating instant nudge with prompt:\n{prompt}")

    # Send to OpenAI
    response = call_openai_completion(prompt)
    message = response.strip()

    print(f"✅ Generated Instant Nudge message:\n{message}")
    return {"message": message}


# Handle sending or scheduling multiple instant nudges
async def handle_instant_nudge_batch(messages: List[dict]):
    db: Session = SessionLocal()
    sent_ids = []

    print(f"📦 Processing {len(messages)} instant nudge message blocks")

    for block in messages:
        customer_ids = block["customer_ids"]
        base_msg = block["message"]
        scheduled_time = block.get("send_datetime_utc")

        print(f"➡️ Block for {len(customer_ids)} customers | Scheduled: {bool(scheduled_time)}")

        for customer_id in customer_ids:
            customer = db.query(Customer).filter(Customer.id == customer_id).first()
            if not customer:
                print(f"⚠️ Skipping unknown customer_id={customer_id}")
                continue

            # Replace placeholder with customer's name
            personalized = base_msg.replace("{customer_name}", customer.customer_name)

            if scheduled_time:
                try:
                    customer_timezone = getattr(customer, "timezone", "UTC")
                    scheduled_time_utc = datetime.fromisoformat(scheduled_time)
                    scheduled_time_utc = scheduled_time_utc.astimezone(pytz.timezone(customer_timezone)).astimezone(pytz.UTC)

                    sms = ScheduledSMS(
                        customer_id=customer_id,
                        business_id=customer.business_id,
                        message=personalized,
                        status="scheduled",
                        send_time=scheduled_time_utc,
                        source="instant_nudge"
                    )
                    db.add(sms)
                    db.flush()  # Get ID before scheduling

                    schedule_sms_task.apply_async(args=[sms.id], eta=scheduled_time_utc)
                    print(f"📅 Scheduled SMS for {customer.customer_name} at {scheduled_time_utc} UTC")
                except Exception as e:
                    print(f"❌ Failed to schedule SMS for {customer.customer_name}: {e}")
                    continue
            else:
                # Send immediately and log in engagements
                business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
                if not business:
                    print(f"⚠️ Skipping customer {customer_id}: business not found.")
                    continue

                send_sms_via_twilio(customer.phone, personalized, business)

                engagement = Engagement(
                    customer_id=customer_id,
                    ai_response=personalized,
                    status="sent",
                    sent_at=datetime.utcnow()
                )
                db.add(engagement)
                print(f"📤 Sent SMS to {customer.customer_name} ({customer.phone})")

            sent_ids.append(customer_id)

    db.commit()
    print(f"✅ Batch complete. Sent immediately to {len(sent_ids)} customers")
    return {"status": "ok", "sent_immediately": sent_ids}