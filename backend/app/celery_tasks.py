# backend/app/celery_tasks.py
# Handles background tasks for sending scheduled SMS messages and generating Co-Pilot nudges.

import asyncio
import logging
from datetime import datetime, timezone as dt_timezone
from typing import Dict, Optional, Union, Any

from fastapi import HTTPException
from app.celery_app import celery_app as celery
from app.database import SessionLocal
from app.models import BusinessProfile, Customer, Message, Engagement, RoadmapMessage
from sqlalchemy.orm import Session
from app.services.twilio_service import send_sms_via_twilio
from app.services.copilot_nudge_generation_service import CoPilotNudgeGenerationService
from app.services.copilot_growth_opportunity_service import CoPilotGrowthOpportunityService

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
    log_prefix = f"[CELERY_TASK process_scheduled_message(MsgID:{message_id})]"
    logger.info(f"{log_prefix} Task started.")

    # NEW: Helper function to update the original RoadmapMessage.
    def update_roadmap_status(db_session: Session, msg_record: Message, new_status: str):
        if isinstance(msg_record.message_metadata, dict):
            roadmap_id = msg_record.message_metadata.get('roadmap_id')
            if roadmap_id:
                roadmap_msg = db_session.query(RoadmapMessage).filter(RoadmapMessage.id == int(roadmap_id)).first()
                if roadmap_msg:
                    roadmap_msg.status = new_status
                    logger.info(f"{log_prefix} Updated original RoadmapMessage (ID: {roadmap_id}) status to '{new_status}'.")

    try:
        logger.info(f"{log_prefix} Fetching Message record from DB.")
        message = db.query(Message).filter(Message.id == message_id).first()

        if not message:
            logger.error(f"{log_prefix} Message record not found in DB. Aborting task.")
            return {"success": False, "error": "Message not found"}

        if message.status != 'scheduled':
            logger.warning(f"{log_prefix} Message status is '{message.status}', not 'scheduled'. Skipping sending.")
            return {"success": False, "status": message.status, "info": "Skipped, status not 'scheduled'"}

        logger.info(f"{log_prefix} Fetching Customer (ID: {message.customer_id}) and Business (ID: {message.business_id}).")
        customer = db.query(Customer).filter(Customer.id == message.customer_id).first()
        if not customer or not customer.phone:
            err_msg = f"{log_prefix} Customer (ID: {message.customer_id}) or phone number not found."
            logger.error(err_msg)
            message.status = "failed"
            update_roadmap_status(db, message, "failed") # NEW: Update roadmap status on failure
            message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': 'Customer/phone not found'}
            db.commit()
            return {"success": False, "error": "Customer or phone not found"}

        if not customer.opted_in:
             err_msg = f"{log_prefix} Customer (ID: {message.customer_id}) is opted-out. Skipping send."
             logger.warning(err_msg)
             message.status = "failed"
             update_roadmap_status(db, message, "failed") # NEW: Update roadmap status on failure
             message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': 'Customer opted out'}
             if message.message_metadata and message.message_metadata.get('source') == 'manual_reply_inbox':
                 engagement_to_fail = db.query(Engagement).filter(Engagement.message_id == message.id).first()
                 if engagement_to_fail:
                     engagement_to_fail.status = "failed"
                     logger.info(f"{log_prefix} Updated related engagement (ID: {engagement_to_fail.id}) status to failed due to opt-out.")
             db.commit()
             return {"success": False, "error": "Customer opted out"}

        business = db.query(BusinessProfile).filter(BusinessProfile.id == message.business_id).first()
        if not business:
            err_msg = f"{log_prefix} Business (ID: {message.business_id}) not found."
            logger.error(err_msg)
            message.status = "failed"
            update_roadmap_status(db, message, "failed") # NEW: Update roadmap status on failure
            message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': 'Business not found'}
            db.commit()
            return {"success": False, "error": "Business not found"}
        
        logger.info(f"{log_prefix} Found Customer: '{customer.customer_name}', Phone: '{customer.phone}'. Found Business: '{business.business_name}'.")

        try:
            logger.info(f"{log_prefix} Calling asyncio.run(send_sms_via_twilio(...)) for customer {customer.phone}.")
            message_sid = asyncio.run(send_sms_via_twilio(
                to=customer.phone,
                message=message.content,
                business=business
            ))
            logger.info(f"{log_prefix} send_sms_via_twilio call completed. Returned SID: {message_sid}")

            logger.info(f"{log_prefix} Attempting to update Message status to 'sent'.")
            message.status = "sent"
            update_roadmap_status(db, message, "sent") # NEW: Update roadmap status on success
            message.sent_at = datetime.now(dt_timezone.utc)
            message.message_metadata = {**(message.message_metadata or {}), 'twilio_sid': message_sid}
            
            if message.message_metadata and message.message_metadata.get('source') == 'manual_reply_inbox':
                logger.info(f"{log_prefix} Source is manual_reply_inbox, finding related engagement.")
                engagement_to_update = db.query(Engagement).filter(Engagement.message_id == message.id).first()
                if engagement_to_update:
                    engagement_to_update.status = "sent"
                    engagement_to_update.sent_at = message.sent_at
                    db.add(engagement_to_update)
                    logger.info(f"{log_prefix} Found engagement (ID: {engagement_to_update.id}) and updated status to 'sent'.")
            
            db.commit()
            logger.info(f"{log_prefix} Database commit successful. Message and potentially Engagement status updated to 'sent'.")
            return {"success": True, "message_sid": message_sid}

        except HTTPException as http_exc_send:
             err_msg = f"HTTPException during send_sms_via_twilio: {http_exc_send.status_code} - {http_exc_send.detail}"
             logger.error(f"{log_prefix} {err_msg}", exc_info=True)
             message.status = "failed"
             update_roadmap_status(db, message, "failed") # NEW: Update roadmap status on failure
             message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': f"Send Error: {http_exc_send.detail}"}
             if message.message_metadata and message.message_metadata.get('source') == 'manual_reply_inbox':
                 engagement_to_fail = db.query(Engagement).filter(Engagement.message_id == message.id).first()
                 if engagement_to_fail:
                     engagement_to_fail.status = "failed"
                     logger.info(f"{log_prefix} Updated related engagement (ID: {engagement_to_fail.id}) status to failed due to send error.")
             db.commit()
             return {"success": False, "error": err_msg}

        except Exception as send_error:
            err_msg = f"Failed during send_sms_via_twilio call: {send_error}"
            logger.error(f"{log_prefix} {err_msg}", exc_info=True)
            message.status = "failed"
            update_roadmap_status(db, message, "failed") # NEW: Update roadmap status on failure
            message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': f"Send Exception: {str(send_error)}"}
            if message.message_metadata and message.message_metadata.get('source') == 'manual_reply_inbox':
                engagement_to_fail = db.query(Engagement).filter(Engagement.message_id == message.id).first()
                if engagement_to_fail:
                    engagement_to_fail.status = "failed"
                    logger.info(f"{log_prefix} Updated related engagement (ID: {engagement_to_fail.id}) status to failed due to send exception.")
            db.commit()
            return {"success": False, "error": err_msg}

    except Exception as e:
        err_msg = f"Unexpected task error: {str(e)}"
        logger.error(f"{log_prefix} {err_msg}", exc_info=True)
        db.rollback()
        if message and message.status == 'scheduled':
            try:
                message_to_fail = db.query(Message).filter(Message.id == message_id).first()
                if message_to_fail:
                     message_to_fail.status = "failed"
                     update_roadmap_status(db, message_to_fail, "failed") # NEW: Update roadmap status on failure
                     message_to_fail.message_metadata = {**(message_to_fail.message_metadata or {}), 'failure_reason': f"Task Error: {str(e)}"}
                     if message_to_fail.message_metadata and message_to_fail.message_metadata.get('source') == 'manual_reply_inbox':
                         engagement_to_fail = db.query(Engagement).filter(Engagement.message_id == message_to_fail.id).first()
                         if engagement_to_fail:
                             engagement_to_fail.status = "failed"
                             logger.info(f"{log_prefix} Updated related engagement (ID: {engagement_to_fail.id}) status to failed due to task error.")
                     db.commit()
                     logger.info(f"{log_prefix} Updated message status to failed after task error.")
            except Exception as update_fail_error:
                logger.error(f"{log_prefix} Could not update message/engagement status to failed after task error: {update_fail_error}", exc_info=True)
                db.rollback()
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

@celery.task(name='generate_sentiment_nudges')
def generate_sentiment_nudges_task(business_id: int) -> Dict[str, any]:
    """
    Celery task to detect both positive and negative sentiment and create CoPilotNudges for a given business.
    """
    log_prefix = f"[CELERY_TASK generate_sentiment_nudges(BusinessID:{business_id})]"
    logger.info(f"{log_prefix} Task started.")
    
    db = None
    try:
        db = SessionLocal()
        nudge_generation_service = CoPilotNudgeGenerationService(db)
        
        logger.info(f"{log_prefix} Detecting positive sentiment...")
        created_positive_nudges = nudge_generation_service.detect_positive_sentiment_and_create_nudges(business_id)
        num_positive_created = len(created_positive_nudges)

        logger.info(f"{log_prefix} Detecting negative sentiment...")
        created_negative_nudges = nudge_generation_service.detect_negative_sentiment_and_create_nudges(business_id)
        num_negative_created = len(created_negative_nudges)
        
        total_nudges_created_this_run = num_positive_created + num_negative_created
        logger.info(f"{log_prefix} Task completed. Total nudges created: {total_nudges_created_this_run}.")
        return {
            "success": True, 
            "business_id": business_id, 
            "positive_nudges_created": num_positive_created,
            "negative_nudges_created": num_negative_created,
        }
    except Exception as e:
        error_message = f"Error during task execution: {str(e)}"
        logger.error(f"{log_prefix} {error_message}", exc_info=True)
        return {"success": False, "business_id": business_id, "error": error_message}
    finally:
        if db:
            db.close()
        logger.info(f"{log_prefix} Task finished.")

@celery.task(name='trigger_strategic_engagement_plan_generation', bind=True, max_retries=2, default_retry_delay=30)
def trigger_strategic_engagement_plan_generation_task(
    self, 
    business_id: int, 
    customer_id: int, 
    trigger_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Celery task to trigger the generation of a strategic engagement plan.
    """
    log_prefix = f"[CELERY_TASK trigger_strategic_plan B:{business_id} C:{customer_id}]"
    logger.info(f"{log_prefix} Task started.")
    
    db = None
    try:
        db = SessionLocal()
        nudge_gen_service = CoPilotNudgeGenerationService(db)
        created_nudge = nudge_gen_service.generate_strategic_engagement_plan(
            business_id=business_id,
            customer_id=customer_id,
            trigger_type="nuanced_sms",
            trigger_data=trigger_data
        )
        
        if created_nudge:
            logger.info(f"{log_prefix} Strategic engagement plan nudge (ID: {created_nudge.id}) created successfully.")
            return {"success": True, "nudge_id": created_nudge.id, "customer_id": customer_id}
        else:
            logger.warning(f"{log_prefix} No strategic engagement plan nudge was created by the service.")
            return {"success": False, "info": "No nudge created by service.", "customer_id": customer_id}
            
    except Exception as e:
        logger.error(f"{log_prefix} Error during strategic plan generation task: {e}", exc_info=True)
        try:
            self.retry(exc=e)
        except Exception as retry_exc:
            logger.error(f"{log_prefix} Failed to enqueue retry for strategic plan generation: {retry_exc}")
        return {"success": False, "error": str(e), "customer_id": customer_id}
    finally:
        if db:
            db.close()
        logger.info(f"{log_prefix} Task finished.")  

@celery.task(name="tasks.run_all_nudge_generation")
def run_all_nudge_generation():
    """
    A periodic Celery task to run all nudge generation services for all businesses.
    This includes reactive (sentiment, event) and proactive (growth) nudges. This
    task should be scheduled to run periodically (e.g., every hour) via Celery Beat.
    """
    db = SessionLocal()
    try:
        logger.info("[CeleryTask] Starting run_all_nudge_generation for all businesses.")
        businesses = db.query(BusinessProfile).all()
        if not businesses:
            logger.info("[CeleryTask] No businesses found to process.")
            return

        for business in businesses:
            log_prefix = f"[CeleryTask B:{business.id}]"
            logger.info(f"{log_prefix} Processing...")

            # --- Initialize Services ---
            reactive_nudge_service = CoPilotNudgeGenerationService(db)
            proactive_growth_service = CoPilotGrowthOpportunityService(db)

            # --- 1. Run Reactive Nudge Generation ---
            # These services look for immediate opportunities in recent messages.
            try:
                logger.info(f"{log_prefix} Running reactive sentiment and event analysis...")
                reactive_nudge_service.detect_positive_sentiment_and_create_nudges(business.id)
                reactive_nudge_service.detect_negative_sentiment_and_create_nudges(business.id)
                reactive_nudge_service.detect_potential_timed_commitments(business.id)
                logger.info(f"{log_prefix} Completed reactive analysis.")
            except Exception as e:
                logger.error(f"{log_prefix} Error during reactive analysis: {e}", exc_info=True)

            # --- 2. Run Proactive Growth Opportunity Generation ---
            # These services perform deeper analysis on customer history.
            try:
                logger.info(f"{log_prefix} Running referral opportunity analysis...")
                proactive_growth_service.identify_referral_opportunities(business.id)
                logger.info(f"{log_prefix} Completed referral opportunity analysis.")
            except Exception as e:
                logger.error(f"{log_prefix} Error during referral opportunity analysis: {e}", exc_info=True)
            
            try:
                logger.info(f"{log_prefix} Running re-engagement opportunity analysis...")
                proactive_growth_service.identify_re_engagement_opportunities(business.id)
                logger.info(f"{log_prefix} Completed re-engagement opportunity analysis.")
            except Exception as e:
                logger.error(f"{log_prefix} Error during re-engagement opportunity analysis: {e}", exc_info=True)

            logger.info(f"{log_prefix} Finished processing.")

    except Exception as e:
        logger.error(f"[CeleryTask] A critical error occurred in run_all_nudge_generation: {e}", exc_info=True)
    finally:
        db.close()
        logger.info("[CeleryTask] run_all_nudge_generation finished and DB session closed.")

# To schedule this task, you would add it to your Celery Beat schedule.
# For example, in your celery_app.py or a config file:
#
# from celery.schedules import crontab
#
# celery_app.conf.beat_schedule = {
#     'run-nudge-generation-every-hour': {
#         'task': 'tasks.run_all_nudge_generation',
#         'schedule': crontab(minute=0),  # Run at the top of every hour
#     },
# }
