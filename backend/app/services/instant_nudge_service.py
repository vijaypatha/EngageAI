# instant_nudge_service.py
# Provides AI-powered SMS generation and handling logic for the Instant Nudge feature.
# Includes generation of personalized messages and logic to send or schedule them.

from typing import List, Dict
from datetime import datetime
import openai
import os
import pytz
import json
import uuid
import traceback

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import BusinessProfile, BusinessOwnerStyle, Message, Engagement, Customer, Conversation
from app.services.twilio_service import send_sms_via_twilio
from app.utils import parse_sms_timing
from app.celery_tasks import schedule_sms_task
from app.services.style_service import get_style_guide


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
async def generate_instant_nudge(topic: str, business_id: int, db: Session) -> dict:
    """Generate a message that perfectly matches the business owner's style"""
    
    # Get business profile
    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        raise Exception("Business not found")
    
    # Get comprehensive style guide
    style_guide = await get_style_guide(business_id, db)
    
    # Format style guide for prompt
    style_elements = {
        'phrases': '\n'.join(style_guide.get('key_phrases', [])),
        'patterns': '\n'.join(style_guide.get('message_patterns', [])),
        'personality': '\n'.join(style_guide.get('personality_traits', [])),
        'special': json.dumps(style_guide.get('special_elements', {}), indent=2)
    }
    
    prompt = f"""
    You are {business.representative_name} from {business.business_name}.
    Write a message about: '{topic}'
    
    YOUR UNIQUE VOICE:
    
    Common Phrases You Use:
    {style_elements['phrases']}
    
    How You Structure Messages:
    {style_elements['patterns']}
    
    Your Personality Traits:
    {style_elements['personality']}
    
    Your Special Elements:
    {style_elements['special']}
    
    CRITICAL RULES:
    1. Write EXACTLY as if you are this person
    2. Use their exact communication patterns
    3. Include their type of phrases and references
    4. Match their personality perfectly
    5. Keep message under 160 characters
    
    Write your message:
    """
    
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert at matching exact communication styles."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )
    
    message = response.choices[0].message.content.strip()
    
    return {"message": message}


# Handle sending or scheduling multiple instant nudges
async def handle_instant_nudge_batch(messages: List[dict]):
    db: Session = SessionLocal()
    message_ids = []
    sent_customers = []
    scheduled_customers = []

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

            # Get or create conversation
            conversation = db.query(Conversation).filter(
                Conversation.customer_id == customer.id,
                Conversation.business_id == customer.business_id,
                Conversation.status == 'active'
            ).first()
            
            if not conversation:
                conversation = Conversation(
                    id=uuid.uuid4(),
                    customer_id=customer.id,
                    business_id=customer.business_id,
                    started_at=datetime.now(pytz.UTC),
                    last_message_at=datetime.now(pytz.UTC),
                    status='active'
                )
                db.add(conversation)
                db.flush()

            if scheduled_time:
                try:
                    customer_timezone = getattr(customer, "timezone") or "UTC"
                    scheduled_time_utc = datetime.fromisoformat(scheduled_time)
                    scheduled_time_utc = scheduled_time_utc.astimezone(pytz.timezone(customer_timezone)).astimezone(pytz.UTC)

                    message = Message(
                        conversation_id=conversation.id,
                        customer_id=customer_id,
                        business_id=customer.business_id,
                        content=personalized,
                        message_type='scheduled',
                        status="scheduled",
                        scheduled_time=scheduled_time_utc,
                        metadata={
                            'source': 'instant_nudge'
                        }
                    )
                    db.add(message)
                    db.flush()  # Get ID before scheduling
                    message_ids.append(message.id)
                    db.commit()  # Commit immediately so scheduled message is visible to frontend
                    schedule_sms_task.apply_async(args=[message.id], eta=scheduled_time_utc)
                    print(f"📅 Scheduled message for {customer.customer_name} at {scheduled_time_utc} UTC")
                except Exception as e:
                    print(f"❌ Failed to schedule message for {customer.customer_name}: {e}")
                    print(f"Traceback: {traceback.format_exc()}")
                    continue
            else:
                # Send immediately and log in engagements
                business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
                if not business:
                    print(f"⚠️ Skipping customer {customer_id}: business not found.")
                    continue

                # Create message record for immediate send
                message = Message(
                    conversation_id=conversation.id,
                    customer_id=customer_id,
                    business_id=customer.business_id,
                    content=personalized,
                    message_type='scheduled',
                    status="sent",
                    scheduled_time=datetime.now(pytz.UTC),
                    sent_at=datetime.now(pytz.UTC),
                    message_metadata={
                        'source': 'instant_nudge'
                    }
                )
                db.add(message)
                db.flush()

                await send_sms_via_twilio(customer.phone, personalized, business)

                engagement = Engagement(
                    customer_id=customer_id,
                    message_id=message.id,
                    ai_response=personalized,
                    status="sent",
                    sent_at=datetime.utcnow()
                )
                db.add(engagement)
                print(f"📤 Sent message to {customer.customer_name} ({customer.phone})")

            if scheduled_time:
                scheduled_customers.append(customer.customer_name)
            else:
                sent_customers.append(customer.customer_name)

    db.commit()
    print(f"✅ Batch complete. {len(sent_customers)} sent now, {len(scheduled_customers)} scheduled for later.")
    if sent_customers:
        print("📤 Sent immediately:", ", ".join(sent_customers))
    if scheduled_customers:
        print("📅 Scheduled:", ", ".join(scheduled_customers))
    return message_ids