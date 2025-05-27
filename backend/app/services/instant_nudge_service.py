# File: backend/app/services/instant_nudge_service.py
# Provides AI-powered SMS generation and handling logic for the Instant Nudge feature.
# Includes generation of personalized messages and logic to send or schedule them.

# --- Standard Imports ---
import logging
import json
import uuid
import traceback
import os
from datetime import datetime, timezone, timedelta # Added timedelta
from typing import List, Dict, Optional, Any # Added Optional, Any

# --- Pydantic and SQLAlchemy Imports ---
from sqlalchemy.orm import Session
import pytz # Make sure pytz is imported
import openai

# --- App Specific Imports ---
from app.database import SessionLocal # Keep SessionLocal if used, or just Session type hint
from app.models import BusinessProfile, Message, Engagement, Customer, Conversation # Ensure all are imported
# Correctly import the NEW celery task that processes messages by ID
# Make sure this task exists and handles sending based on Message ID
from app.celery_tasks import process_scheduled_message_task # Assuming this task exists
from app.services.style_service import get_style_guide # Assuming async
from app.services.twilio_service import TwilioService # Import the service class
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# --- generate_instant_nudge Function (Keep As Is) ---
async def generate_instant_nudge(topic: str, business_id: int, db: Session) -> Dict[str, Any]:
    """Generate a message that perfectly matches the business owner's style"""
    # Get business profile
    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        # Use ValueError or custom exception for service layer errors
        raise ValueError(f"Business not found for ID: {business_id}")

    # Get comprehensive style guide
    style_guide_data = await get_style_guide(business_id, db) # Assuming async

    # Format style guide for prompt
    style_elements = {
        'phrases': '\n'.join(style_guide_data.get('key_phrases', [])),
         # Ensure message_patterns exists and is a dict before accessing subkeys
        'patterns': '\n'.join(style_guide_data.get('message_patterns', {}).get('patterns', [])),
        'personality': '\n'.join(style_guide_data.get('personality_traits', [])),
        'special': json.dumps(style_guide_data.get('special_elements', {}), indent=2),
         # Add style notes if they exist in your guide structure
        'style_notes': json.dumps(style_guide_data.get('style_notes', {}), indent=2)
    }

    prompt = f"""
    You are {business.representative_name or 'the owner'} from {business.business_name}.
    Write a short, friendly SMS message (under 160 chars) about: '{topic}'
    Use the placeholder {{customer_name}} where the customer's name should go.

    YOUR UNIQUE VOICE:
    Common Phrases You Use:
    {style_elements['phrases']}
    How You Structure Messages:
    {style_elements['patterns']}
    Your Personality Traits:
    {style_elements['personality']}
    Your Special Elements:
    {style_elements['special']}
    Your Style Notes:
    {style_elements['style_notes']}

    CRITICAL RULES:
    1. Write EXACTLY as if you are this person, matching their unique style.
    2. Use their exact communication patterns and phrases naturally.
    3. Keep message under 160 characters.
    4. MUST include the placeholder {{customer_name}}.
    5. End appropriately (e.g., with representative name if available).

    Write your message:
    """

    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o", # Or your preferred model
            messages=[
                {"role": "system", "content": "You are an expert at matching exact communication styles for SMS."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=100 # Keep it concise
        )
        message_content = response.choices[0].message.content.strip()

        # Basic check for placeholder
        if "{customer_name}" not in message_content:
             logger.warning("Generated message missing {customer_name} placeholder. Adding it.")
             # Attempt a simple fix or add instructions to regenerate
             message_content = f"Hi {{customer_name}}, {message_content}" # Example fix

        return {"message": message_content}

    except Exception as e:
        logger.error(f"OpenAI API call failed during nudge generation: {e}", exc_info=True)
        raise Exception(f"AI message generation failed: {e}") from e

# --- REFACTORED: handle_instant_nudge_batch Function ---
async def handle_instant_nudge_batch(
    db: Session, # Pass Session directly
    business_id: int,
    customer_ids: List[int],
    message_content: str, # The pre-generated message template
    send_datetime_iso: Optional[str] = None # Optional ISO string for scheduling
) -> Dict[str, Any]:
    """
    Handles sending or scheduling an Instant Nudge message to a list of customers.
    """
    if not customer_ids:
        logger.warning("handle_instant_nudge_batch called with empty customer_ids list.")
        return {"processed_message_ids": [], "sent_count": 0, "scheduled_count": 0, "failed_count": 0}

    processed_message_ids = []
    sent_count = 0
    scheduled_count = 0
    failed_count = 0

    # --- Pre-fetch Business Info ---
    # Fetch once outside the loop for efficiency
    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        # If the business doesn't exist, we can't proceed for any customer
        raise ValueError(f"Business not found for ID: {business_id}")

    # --- Determine if Scheduling or Sending Immediately ---
    is_scheduling = False
    scheduled_time_utc: Optional[datetime] = None
    now_utc = datetime.now(timezone.utc)

    if send_datetime_iso:
        try:
            # Attempt to parse the ISO string
            parsed_dt = datetime.fromisoformat(send_datetime_iso.replace('Z', '+00:00')) # Handle 'Z' if present
            # Ensure it's timezone-aware UTC
            if parsed_dt.tzinfo is None:
                 # Assume UTC if no timezone provided in string - adjust if frontend sends local time
                 scheduled_time_utc = pytz.UTC.localize(parsed_dt)
                 logger.warning(f"Received schedule time without timezone, assuming UTC: {send_datetime_iso} -> {scheduled_time_utc}")
            else:
                 scheduled_time_utc = parsed_dt.astimezone(pytz.UTC)

            # Check if the scheduled time is in the future (allow a small buffer)
            if scheduled_time_utc > (now_utc - timedelta(minutes=1)):
                is_scheduling = True
                logger.info(f"Scheduling messages for {scheduled_time_utc} UTC.")
            else:
                logger.info(f"Scheduled time {send_datetime_iso} is in the past. Sending immediately.")

        except ValueError as e:
            logger.error(f"Invalid ISO format for send_datetime_iso: '{send_datetime_iso}'. Error: {e}. Sending immediately.")
            # Fallback to immediate send if parsing fails

    # --- Initialize Twilio Service (if sending immediately) ---
    twilio_service = None
    if not is_scheduling:
         twilio_service = TwilioService(db) # Initialize only if needed

    # --- Process Each Customer ---
    for customer_id in customer_ids:
        # Wrap per-customer logic in try/except to allow batch continuation on single failure
        message_record_id = None # Track ID for potential rollback/logging
        try:
            customer = db.query(Customer).filter(Customer.id == customer_id).first()
            if not customer:
                logger.warning(f"Skipping unknown customer_id={customer_id} in batch.")
                failed_count += 1
                continue
            if not customer.opted_in:
                logger.warning(f"Skipping opted-out customer_id={customer_id} (Name: {customer.customer_name}).")
                failed_count += 1
                continue

            # Personalize message
            personalized_message = message_content.replace("{customer_name}", customer.customer_name)
            if len(personalized_message) > 1600: # Twilio segment limit check
                 logger.warning(f"Message for customer {customer_id} might exceed segment limits ({len(personalized_message)} chars).")
                 # Decide: truncate, skip, or send anyway? Let's send for now.

            # Get or create conversation
            conversation = db.query(Conversation).filter(
                Conversation.customer_id == customer.id,
                Conversation.business_id == business_id, # Use business_id passed in
                Conversation.status == 'active'
            ).first()

            if not conversation:
                conversation = Conversation(
                    id=uuid.uuid4(),
                    customer_id=customer.id,
                    business_id=business_id,
                    started_at=now_utc, # Use consistent UTC time
                    last_message_at=now_utc,
                    status='active'
                )
                db.add(conversation)
                db.flush() # Get conversation.id assigned

            # --- Create Message DB Record ---
            message_status = "scheduled" if is_scheduling else "pending_send" # Use intermediate status for immediate send
            message = Message(
                conversation_id=conversation.id,
                customer_id=customer_id,
                business_id=business_id,
                content=personalized_message,
                message_type='scheduled', # Consistent type for outbound planned messages
                status=message_status,
                scheduled_time=scheduled_time_utc if is_scheduling else now_utc, # Store target time or now
                sent_at=None, # sent_at is set upon successful delivery confirmation (or attempt for immediate)
                message_metadata={'source': 'instant_nudge'}
            )
            db.add(message)
            db.flush() # Get message.id
            message_record_id = message.id # Store for logging/Celery

            # --- Perform Action: Schedule or Send ---
            if is_scheduling:
                # Schedule Celery Task
                try:
                    # Ensure process_scheduled_message_task takes message.id as arg
                    process_scheduled_message_task.apply_async(args=[message.id], eta=scheduled_time_utc)
                    # Commit *after* successful queuing
                    db.commit()
                    processed_message_ids.append(message.id)
                    scheduled_count += 1
                    logger.info(f"✅ Successfully scheduled Message ID {message.id} for customer {customer_id} at {scheduled_time_utc} UTC.")
                except Exception as celery_err:
                    db.rollback() # Rollback message creation if Celery fails
                    failed_count += 1
                    logger.error(f"❌ Failed to schedule Celery task for Message ID {message_record_id} (Customer {customer_id}): {celery_err}", exc_info=True)

            else:
                # Send Immediately using Twilio Service
                try:
                    # Use the TwilioService instance initialized earlier
                    sent_sid = await twilio_service.send_sms(
                         to=customer.phone,
                         message_body=personalized_message, # <<< CORRECTED ARGUMENT NAME
                         business=business, # Pass the fetched business object
                         customer=customer, # Recommended: Also pass the customer object for consistency with consent checks
                         is_direct_reply=False # Assuming instant nudges are proactive, not direct replies
                         )

                    # Update status and sent_at on successful send attempt
                    message.status = "sent" # Mark as sent immediately on successful API call
                    message.sent_at = datetime.now(timezone.utc)
                    db.add(message) # Re-add to session after modification

                    # Optionally create Engagement record for immediate sends
                    engagement = Engagement(
                         customer_id=customer_id,
                         message_id=message.id,
                         ai_response=personalized_message, # Log sent message
                         status="sent",
                         sent_at=message.sent_at
                         )
                    db.add(engagement)

                    db.commit() # Commit message update and engagement together
                    processed_message_ids.append(message.id)
                    sent_count += 1
                    logger.info(f"✅ Successfully sent immediate SMS for Message ID {message.id} (Customer {customer_id}). SID: {sent_sid}")

                except HTTPException as http_send_err:
                    # Handle errors raised by twilio_service.send_sms (e.g., config error)
                    db.rollback()
                    failed_count += 1
                    logger.error(f"❌ HTTP error sending immediate SMS for Message ID {message_record_id} (Customer {customer_id}): {http_send_err.status_code} - {http_send_err.detail}")
                    # Optionally update message status to 'failed' here
                except Exception as send_err:
                     # Catch other unexpected send errors
                     db.rollback()
                     failed_count += 1
                     logger.error(f"❌ Failed to send immediate SMS for Message ID {message_record_id} (Customer {customer_id}): {send_err}", exc_info=True)
                     # Optionally update message status to 'failed'

        except Exception as per_customer_err:
             # Catch unexpected errors within the customer loop
             failed_count += 1
             logger.error(f"❌ Unexpected error processing customer_id={customer_id} in batch: {per_customer_err}", exc_info=True)
             # Rollback any partial changes for this customer
             db.rollback()

    # --- Return Summary ---
    logger.info(f"Batch processing summary: Sent={sent_count}, Scheduled={scheduled_count}, Failed/Skipped={failed_count}")
    return {
        "processed_message_ids": processed_message_ids, # IDs where processing was attempted and might have succeeded
        "sent_count": sent_count,
        "scheduled_count": scheduled_count,
        "failed_count": failed_count
    }

# Note: Ensure Session management (SessionLocal() and db.close()) is handled correctly
# if this function is called directly without FastAPI's Depends(get_db).
# If called *only* from routes using Depends(get_db), passing the db session is sufficient.