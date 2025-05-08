# backend/app/celery_tasks.py
# Handles background tasks for sending scheduled SMS messages based on the Message model.

import asyncio
import logging
from datetime import datetime, timezone as dt_timezone # Alias timezone to avoid conflict
from typing import Dict, Optional, Union

from app.celery_app import celery_app as celery
from app.database import SessionLocal
from app.models import BusinessProfile, Customer, Message, Engagement # Added Engagement
# Use the Twilio service that handles sending
# Assuming send_sms_via_twilio exists and calls TwilioService.send_sms correctly
from app.services.twilio_service import send_sms_via_twilio

# Configure logging
logger = logging.getLogger(__name__)

@celery.task(name='ping')
def ping() -> str:
    logger.info("Celery ping task executed.")
    return "pong"


@celery.task(name='process_scheduled_message', bind=True, max_retries=3, default_retry_delay=60)
def process_scheduled_message_task(self, message_id: int) -> Dict[str, Union[bool, str, None]]:
    """
    Processes a scheduled message stored in the Message table by its ID.
    Fetches message, customer, and business details, sends the SMS via Twilio,
    and updates the message status accordingly ('sent' or 'failed').
    **Also updates related Engagement status if source is 'manual_reply_inbox'.**
    """
    db = SessionLocal()
    message = None
    engagement_to_update = None # To hold related engagement if needed
    log_prefix = f"[CELERY_TASK process_scheduled_message(MsgID:{message_id})]"
    logger.info(f"{log_prefix} Task started.")

    try:
        # Step 1: Fetch the main message record
        logger.info(f"{log_prefix} Fetching Message record from DB.")
        message = db.query(Message).filter(Message.id == message_id).first()

        if not message:
            logger.error(f"{log_prefix} Message record not found in DB. Aborting task.")
            return {"success": False, "error": "Message not found"}

        logger.info(f"{log_prefix} Found Message. Current status: '{message.status}', Scheduled time: {message.scheduled_time}, Content: '{message.content[:50]}...'")

        # Step 2: Check if the message is still valid for sending
        if message.status != 'scheduled':
            logger.warning(f"{log_prefix} Message status is '{message.status}', not 'scheduled'. Skipping sending.")
            return {"success": False, "status": message.status, "info": "Skipped, status not 'scheduled'"}

        # Step 3: Fetch related customer and business profiles
        logger.info(f"{log_prefix} Fetching Customer (ID: {message.customer_id}) and Business (ID: {message.business_id}).")
        customer = db.query(Customer).filter(Customer.id == message.customer_id).first()
        if not customer or not customer.phone:
            err_msg = f"{log_prefix} Customer (ID: {message.customer_id}) or phone number not found."
            logger.error(err_msg)
            message.status = "failed"
            message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': 'Customer/phone not found'}
            db.commit()
            return {"success": False, "error": "Customer or phone not found"}

        if not customer.opted_in:
             err_msg = f"{log_prefix} Customer (ID: {message.customer_id}) is opted-out. Skipping send."
             logger.warning(err_msg)
             message.status = "failed"
             message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': 'Customer opted out'}
              # --- Find and update related Engagement if manual reply ---
             if message.message_metadata and message.message_metadata.get('source') == 'manual_reply_inbox':
                 engagement_to_fail = db.query(Engagement).filter(Engagement.message_id == message.id).first()
                 if engagement_to_fail:
                     engagement_to_fail.status = "failed" # Match message status
                     logger.info(f"{log_prefix} Updated related engagement (ID: {engagement_to_fail.id}) status to failed due to opt-out.")
                 else:
                      logger.warning(f"{log_prefix} Could not find related engagement for message_id {message.id} to mark as failed.")
             # --- End Engagement update ---
             db.commit()
             return {"success": False, "error": "Customer opted out"}

        business = db.query(BusinessProfile).filter(BusinessProfile.id == message.business_id).first()
        if not business:
            err_msg = f"{log_prefix} Business (ID: {message.business_id}) not found."
            logger.error(err_msg)
            message.status = "failed"
            message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': 'Business not found'}
            db.commit()
            return {"success": False, "error": "Business not found"}
        
        logger.info(f"{log_prefix} Found Customer: '{customer.customer_name}', Phone: '{customer.phone}'. Found Business: '{business.business_name}'.")

        # Step 4: Attempt to send the SMS via Twilio Service
        try:
            logger.info(f"{log_prefix} Calling asyncio.run(send_sms_via_twilio(...)) for customer {customer.phone}.")
            # Ensure the business object passed contains the necessary fields (twilio_number, messaging_service_sid)
            logger.debug(f"{log_prefix} Business details for send: twilio_number='{business.twilio_number}', msid='{business.messaging_service_sid}'")
            
            # ***** CRITICAL: Ensure asyncio event loop handling is correct for your Celery setup *****
            # Simple asyncio.run might cause issues in some Celery configurations.
            # Consider using celery[asyncio] if problems persist.
            message_sid = asyncio.run(send_sms_via_twilio(
                to=customer.phone,
                message=message.content,
                business=business
            ))
            logger.info(f"{log_prefix} send_sms_via_twilio call completed. Returned SID: {message_sid}")

            # Step 5a: Update message status to 'sent'
            logger.info(f"{log_prefix} Attempting to update Message status to 'sent'.")
            message.status = "sent"
            message.sent_at = datetime.now(dt_timezone.utc)
            message.message_metadata = {**(message.message_metadata or {}), 'twilio_sid': message_sid}
            
            # --- Update related Engagement status ---
            if message.message_metadata and message.message_metadata.get('source') == 'manual_reply_inbox':
                logger.info(f"{log_prefix} Source is manual_reply_inbox, finding related engagement.")
                engagement_to_update = db.query(Engagement).filter(Engagement.message_id == message.id).first()
                if engagement_to_update:
                    engagement_to_update.status = "sent" # Update engagement status
                    engagement_to_update.sent_at = message.sent_at # Align timestamp
                    db.add(engagement_to_update) # Add to session for commit
                    logger.info(f"{log_prefix} Found engagement (ID: {engagement_to_update.id}) and updated status to 'sent'.")
                else:
                    logger.warning(f"{log_prefix} Could not find related engagement for message_id {message.id} to mark as sent.")
            # --- End Engagement update ---

            db.commit()
            logger.info(f"{log_prefix} Database commit successful. Message and potentially Engagement status updated to 'sent'.")
            return {"success": True, "message_sid": message_sid}

        except HTTPException as http_exc_send:
             # Catch HTTP exceptions specifically from the send function (e.g., config errors)
             err_msg = f"HTTPException during send_sms_via_twilio: {http_exc_send.status_code} - {http_exc_send.detail}"
             logger.error(f"{log_prefix} {err_msg}", exc_info=True)
             message.status = "failed"
             message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': f"Send Error: {http_exc_send.detail}"}
             # --- Update related Engagement status ---
             if message.message_metadata and message.message_metadata.get('source') == 'manual_reply_inbox':
                 engagement_to_fail = db.query(Engagement).filter(Engagement.message_id == message.id).first()
                 if engagement_to_fail:
                     engagement_to_fail.status = "failed"
                     logger.info(f"{log_prefix} Updated related engagement (ID: {engagement_to_fail.id}) status to failed due to send error.")
             # --- End Engagement update ---
             db.commit()
             return {"success": False, "error": err_msg}

        except Exception as send_error:
            # Catch other errors during the send process
            err_msg = f"Failed during send_sms_via_twilio call: {send_error}"
            logger.error(f"{log_prefix} {err_msg}", exc_info=True)
            message.status = "failed"
            message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': f"Send Exception: {str(send_error)}"}
            # --- Update related Engagement status ---
            if message.message_metadata and message.message_metadata.get('source') == 'manual_reply_inbox':
                engagement_to_fail = db.query(Engagement).filter(Engagement.message_id == message.id).first()
                if engagement_to_fail:
                    engagement_to_fail.status = "failed"
                    logger.info(f"{log_prefix} Updated related engagement (ID: {engagement_to_fail.id}) status to failed due to send exception.")
            # --- End Engagement update ---
            db.commit()
            # Decide whether to retry
            # self.retry(exc=send_error) # Uncomment to enable retries for generic send errors
            return {"success": False, "error": err_msg}

    except Exception as e:
        # Catch unexpected errors during the task setup (DB fetches, etc.)
        err_msg = f"Unexpected task error: {str(e)}"
        logger.error(f"{log_prefix} {err_msg}", exc_info=True)
        db.rollback()

        if message and message.status == 'scheduled':
            try:
                # Fetch again in a new query within this exception block if needed
                message_to_fail = db.query(Message).filter(Message.id == message_id).first()
                if message_to_fail:
                     message_to_fail.status = "failed"
                     message_to_fail.message_metadata = {**(message_to_fail.message_metadata or {}), 'failure_reason': f"Task Error: {str(e)}"}
                     # --- Update related Engagement status ---
                     if message_to_fail.message_metadata and message_to_fail.message_metadata.get('source') == 'manual_reply_inbox':
                         engagement_to_fail = db.query(Engagement).filter(Engagement.message_id == message_to_fail.id).first()
                         if engagement_to_fail:
                             engagement_to_fail.status = "failed"
                             logger.info(f"{log_prefix} Updated related engagement (ID: {engagement_to_fail.id}) status to failed due to task error.")
                     # --- End Engagement update ---
                     db.commit()
                     logger.info(f"{log_prefix} Updated message status to failed after task error.")
            except Exception as update_fail_error:
                logger.error(f"{log_prefix} Could not update message/engagement status to failed after task error: {update_fail_error}", exc_info=True)
                db.rollback()

        # Retry the task for potentially transient issues
        try:
            logger.warning(f"{log_prefix} Retrying task due to unexpected error.")
            self.retry(exc=e)
        except Exception as retry_error:
             logger.error(f"{log_prefix} Failed to enqueue retry: {retry_error}")

        return {"success": False, "error": err_msg}

    finally:
        if db:
            db.close()
        logger.info(f"{log_prefix} Task finished.")