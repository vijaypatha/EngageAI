# File: backend/app/services/instant_nudge_service.py
# Provides AI-powered SMS generation and handling logic for the Instant Nudge feature.
# Includes generation of personalized messages and logic to send or schedule them.

from typing import List, Dict
from datetime import datetime, timezone # Added timezone import
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
# Removed unused utils import: from app.utils import parse_sms_timing
# Correctly import the NEW celery task along with potentially others
from app.celery_tasks import process_scheduled_message_task # Removed schedule_sms_task import as it's not used here
from app.services.style_service import get_style_guide


# Helper: Call OpenAI to generate short SMS message
# (Keep this function as is)
async def call_openai_completion(prompt: str) -> str:
    # ... implementation ...
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
# (Keep this function as is)
async def generate_instant_nudge(topic: str, business_id: int, db: Session) -> dict:
    """Generate a message that perfectly matches the business owner's style"""
    # ... implementation ...
    # Get business profile
    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        raise Exception("Business not found")

    # Get comprehensive style guide
    # Ensure get_style_guide is async if called with await
    style_guide_data = await get_style_guide(business_id, db) # Assuming get_style_guide is async

    # Format style guide for prompt
    style_elements = {
        'phrases': '\n'.join(style_guide_data.get('key_phrases', [])),
        'patterns': '\n'.join(style_guide_data.get('message_patterns', {}).get('patterns', [])), # Adjusted based on potential structure
        'personality': '\n'.join(style_guide_data.get('personality_traits', [])),
        'special': json.dumps(style_guide_data.get('special_elements', {}), indent=2)
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

    message_content = response.choices[0].message.content.strip() # Renamed variable

    return {"message": message_content}


# Handle sending or scheduling multiple instant nudges
async def handle_instant_nudge_batch(messages: List[dict]):
    db: Session = SessionLocal()
    message_ids = []
    sent_customers = []
    scheduled_customers = []

    print(f"📦 Processing {len(messages)} instant nudge message blocks")

    # Use a single try...finally block for database session management
    try:
        for block in messages:
            customer_ids = block["customer_ids"]
            base_msg = block["message"]
            scheduled_time_str = block.get("send_datetime_utc") # Renamed for clarity

            print(f"➡️ Block for {len(customer_ids)} customers | Scheduled: {bool(scheduled_time_str)}")

            for customer_id in customer_ids:
                # Wrap per-customer logic in try/except to prevent one failure from stopping others
                try:
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
                            # Use timezone aware datetime
                            started_at=datetime.now(timezone.utc),
                            last_message_at=datetime.now(timezone.utc),
                            status='active'
                        )
                        db.add(conversation)
                        db.flush() # Flush to get conversation ID if needed

                    # --- Scheduling Logic ---
                    if scheduled_time_str:
                        # Use nested try/except for scheduling specific errors
                        try:
                            # --- Timezone conversion ---
                            customer_timezone = getattr(customer, "timezone") or "UTC"
                            # Parse ISO string from frontend
                            scheduled_time_naive = datetime.fromisoformat(scheduled_time_str)

                            # Ensure it's timezone-aware before converting, assuming input is local time
                            if scheduled_time_naive.tzinfo is None:
                                local_tz = pytz.timezone(customer_timezone)
                                scheduled_time_aware = local_tz.localize(scheduled_time_naive)
                            else:
                                scheduled_time_aware = scheduled_time_naive # Already aware

                            # Convert to UTC for storing and scheduling
                            scheduled_time_utc = scheduled_time_aware.astimezone(pytz.UTC)

                            # --- Create Message Record ---
                            message = Message(
                                conversation_id=conversation.id,
                                customer_id=customer_id,
                                business_id=customer.business_id,
                                content=personalized,
                                message_type='scheduled', # Consistent type
                                status="scheduled",
                                scheduled_time=scheduled_time_utc,
                                # Use correct key name 'metadata' if model expects it
                                message_metadata={
                                    'source': 'instant_nudge'
                                }
                            )
                            db.add(message)
                            db.flush()  # Get message.id
                            message_id_val = message.id # Store the ID
                            message_ids.append(message_id_val)
                            # Commit should happen AFTER Celery task is successfully queued,
                            # otherwise the task might run before commit and not find the message.
                            # db.commit() # Moved commit lower

                            # --- Schedule Celery Task ---
                            try:
                                process_scheduled_message_task.apply_async(args=[message_id_val], eta=scheduled_time_utc)
                                print(f"✅ Correctly scheduled Celery task 'process_scheduled_message_task' for Message ID {message_id_val} at {scheduled_time_utc} UTC")
                                # Now commit the message record since Celery task is queued
                                db.commit()
                                scheduled_customers.append(customer.customer_name) # Append only on successful scheduling AND commit
                            except Exception as celery_err:
                                print(f"❌ Failed to schedule Celery task for Message ID {message_id_val}: {celery_err}")
                                db.rollback() # Rollback message creation if Celery fails
                                # Do not add to scheduled_customers list

                        except Exception as schedule_block_err:
                            print(f"❌ Failed during scheduling block for {customer.customer_name}: {schedule_block_err}")
                            print(f"Traceback: {traceback.format_exc()}")
                            db.rollback() # Rollback any partial changes for this customer/block

                    # --- Immediate Send Logic ---
                    else:
                        business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
                        if not business:
                            print(f"⚠️ Skipping customer {customer_id}: business not found for immediate send.")
                            continue # Skip this customer

                        # --- Create Message Record ---
                        message = Message(
                            conversation_id=conversation.id,
                            customer_id=customer_id,
                            business_id=customer.business_id,
                            content=personalized,
                            message_type='scheduled', # Consistent type
                            status="sent", # Set status to sent immediately
                            scheduled_time=datetime.now(timezone.utc), # Record attempt time
                            sent_at=datetime.now(timezone.utc), # Record attempt time as sent_at
                            message_metadata={ # Use correct key name
                                'source': 'instant_nudge'
                            }
                        )
                        db.add(message)
                        db.flush() # Get message.id

                        # --- Call Twilio ---
                        try:
                            # Ensure await is used!
                            await send_sms_via_twilio(customer.phone, personalized, business)
                            print(f"✅ Twilio send successful for customer {customer.customer_name} ({customer.phone})")

                            # --- Create Engagement Record ---
                            engagement = Engagement(
                                customer_id=customer_id,
                                message_id=message.id, # Link to the message record
                                ai_response=personalized, # Storing the sent message here
                                status="sent", # Match message status
                                sent_at=message.sent_at # Use the same timestamp
                            )
                            db.add(engagement)
                            db.commit() # Commit message and engagement together after successful send
                            message_ids.append(message.id) # Add ID after successful commit
                            sent_customers.append(customer.customer_name) # Add to list only on success

                        except Exception as send_err:
                            print(f"❌ Failed to send immediate SMS to {customer.customer_name}: {send_err}")
                            db.rollback() # Rollback message/engagement creation if send fails
                            # Update message status to 'failed' if needed, but requires another commit
                            # message.status = 'failed'
                            # db.add(message) # Add again if rolled back
                            # db.commit()

                except Exception as per_customer_err:
                     print(f"❌ Unexpected error processing customer_id={customer_id}: {per_customer_err}")
                     print(f"Traceback: {traceback.format_exc()}")
                     db.rollback() # Rollback any changes for this specific customer

        # Final status logging
        print(f"✅ Batch processing complete. {len(sent_customers)} sent now, {len(scheduled_customers)} successfully scheduled.")
        if sent_customers:
            print("📤 Sent immediately:", ", ".join(sent_customers))
        if scheduled_customers:
            print("📅 Scheduled:", ", ".join(scheduled_customers))

        return {"processed_message_ids": message_ids} # Return IDs that were at least attempted

    finally:
        db.close() # Ensure DB session is closed