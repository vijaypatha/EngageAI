# backend/app/celery_tasks.py
# Handles background tasks for sending scheduled SMS messages based on the Message model.

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Union

from app.celery_app import celery_app as celery
from app.database import SessionLocal
# --- Use the Message model as the source of truth for scheduled messages ---
from app.models import BusinessProfile, Customer, Message
# --- Use the Twilio service that handles sending ---
from app.services.twilio_service import send_sms_via_twilio

# Configure logging
logger = logging.getLogger(__name__)


@celery.task(name='ping')
def ping() -> str:
    """Simple ping task for testing Celery setup."""
    logger.info("Celery ping task executed.")
    return "pong"


@celery.task(name='process_scheduled_message', bind=True, max_retries=3, default_retry_delay=60)
def process_scheduled_message_task(self, message_id: int) -> Dict[str, Union[bool, str, None]]:
    """
    Processes a scheduled message stored in the Message table by its ID.

    Fetches message, customer, and business details, sends the SMS via Twilio,
    and updates the message status accordingly ('sent' or 'failed').

    Args:
        message_id: The ID of the Message record to process.

    Returns:
        A dictionary indicating success or failure, and including the
        Twilio message SID if successful, or an error message if failed.
    """
    db = SessionLocal()
    message = None  # Define message outside try for potential status update in except/retry
    log_prefix = f"[TASK_process_scheduled_message(ID:{message_id})]" # For easier log tracking
    logger.info(f"{log_prefix} Task started.")

    try:
        # Step 1: Fetch the main message record
        # Ensure relationships are loaded if needed directly, though fetching separately is also fine.
        message = db.query(Message).filter(Message.id == message_id).first()

        if not message:
            logger.error(f"{log_prefix} Message record not found in DB.")
            # No retry needed if the record doesn't exist.
            return {"success": False, "error": "Message not found"}

        logger.info(f"{log_prefix} Found message. Current status: '{message.status}', Scheduled time: {message.scheduled_time}")

        # Step 2: Check if the message is still valid for sending
        # It should be in 'scheduled' state. If it's 'sent', 'failed', 'deleted', etc., skip.
        if message.status != 'scheduled':
            logger.warning(f"{log_prefix} Message status is '{message.status}', not 'scheduled'. Skipping sending.")
            # Don't mark as failed, just report the current status.
            return {"success": False, "status": message.status, "info": "Skipped, status not 'scheduled'"}

        # Optional: Check if the scheduled time is significantly past due (indicates potential scheduler issue)
        # now_utc = datetime.now(timezone.utc)
        # if message.scheduled_time and (now_utc - message.scheduled_time).total_seconds() > 3600: # e.g., 1 hour late
        #     logger.warning(f"{log_prefix} Message is significantly past its scheduled time ({message.scheduled_time}). Processing anyway.")

        # Step 3: Fetch related customer and business profiles
        customer = db.query(Customer).filter(Customer.id == message.customer_id).first()
        if not customer or not customer.phone:
            logger.error(f"{log_prefix} Customer (ID: {message.customer_id}) or phone number not found.")
            message.status = "failed"
            message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': 'Customer/phone not found'}
            db.commit()
            return {"success": False, "error": "Customer or phone not found"}

        # Check customer opt-in status again before sending
        if not customer.opted_in:
             logger.warning(f"{log_prefix} Customer (ID: {message.customer_id}) is opted-out. Skipping send.")
             message.status = "failed" # Or a new status like 'skipped_opt_out'
             message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': 'Customer opted out'}
             db.commit()
             return {"success": False, "error": "Customer opted out"}


        business = db.query(BusinessProfile).filter(BusinessProfile.id == message.business_id).first()
        if not business:
            logger.error(f"{log_prefix} Business (ID: {message.business_id}) not found.")
            message.status = "failed"
            message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': 'Business not found'}
            db.commit()
            return {"success": False, "error": "Business not found"}

        # Step 4: Attempt to send the SMS via Twilio Service
        try:
            logger.info(f"{log_prefix} Attempting to send SMS to {customer.phone} via Twilio service.")
            # Use asyncio.run to call the async send_sms_via_twilio function from the sync Celery task
            # Note: Requires Python 3.7+. Ensure your Celery worker environment supports this.
            # If using older Python or encountering issues, the TwilioService might need a sync wrapper.
            message_sid = asyncio.run(send_sms_via_twilio(
                to=customer.phone,
                message=message.content,
                business=business  # Pass the full business object
            ))

            # If send_sms_via_twilio raises an exception, it's caught below.
            # If it returns successfully, we assume submission to Twilio was okay.
            logger.info(f"{log_prefix} SMS submitted successfully to Twilio. SID: {message_sid}")

            # Step 5a: Update message status to 'sent' on successful submission
            message.status = "sent"
            message.sent_at = datetime.now(timezone.utc)
            message.message_metadata = {**(message.message_metadata or {}), 'twilio_sid': message_sid}
            db.commit()
            logger.info(f"{log_prefix} Message status updated to 'sent'.")
            return {"success": True, "message_sid": message_sid}

        except Exception as send_error:
            # Catch errors specifically from the send_sms_via_twilio call (e.g., Twilio API errors, config issues)
            logger.error(f"{log_prefix} Failed to send SMS: {send_error}", exc_info=True)

            # Step 5b: Update status to 'failed'
            message.status = "failed"
            message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': str(send_error)}
            db.commit()
            logger.info(f"{log_prefix} Message status updated to 'failed'.")

            # Decide whether to retry based on the error type
            # Example: Retry for temporary network issues, not for invalid number format
            if isinstance(send_error, asyncio.TimeoutError): # Example retry condition
                logger.warning(f"{log_prefix} Retrying due to timeout...")
                self.retry(exc=send_error)

            return {"success": False, "error": str(send_error)}

    except Exception as e:
        # Catch unexpected errors during the task execution (DB issues, etc.)
        logger.error(f"{log_prefix} Unexpected error: {str(e)}", exc_info=True)
        db.rollback() # Rollback any potential partial changes

        # Update status to 'failed' if possible, even on unexpected errors
        if message and message.status == 'scheduled': # Only update if not already failed/sent
            try:
                message.status = "failed"
                message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': f"Unexpected task error: {str(e)}"}
                db.commit() # Commit the failure status
            except Exception as update_fail_error:
                logger.error(f"{log_prefix} Could not update message status to failed after unexpected error: {update_fail_error}")
                db.rollback()

        # Retry the task for potentially transient issues
        try:
            self.retry(exc=e)
        except Exception as retry_error:
             logger.error(f"{log_prefix} Failed to retry task: {retry_error}")

        # Return failure if retries exhausted or retry fails
        return {"success": False, "error": f"Unexpected task error: {str(e)}"}

    finally:
        # Ensure the database session is always closed
        if db:
            db.close()
        logger.info(f"{log_prefix} Task finished.")

# --- Removed schedule_sms_task and process_scheduled_sms tasks ---
# Ensure that all code previously calling these tasks is updated to:
# 1. Create a `Message` record in the database with status='scheduled' and the correct `scheduled_time`.
# 2. Call `process_scheduled_message_task.apply_async(args=[message.id], eta=message.scheduled_time)`.