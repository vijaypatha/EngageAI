# Handles background tasks for sending and scheduling SMS messages
# Business owners can schedule messages that will be sent automatically at the right time
from datetime import datetime
import logging
from typing import Dict, Optional, Union


from app.config import settings
from app.database import SessionLocal
from app.models import ScheduledSMS
from app.services.twilio_service import send_sms_via_twilio
from app.celery_app import celery_app as celery

# Configure logging
logger = logging.getLogger(__name__)



@celery.task(name='ping')
def ping() -> str:
    """Simple ping task for testing Celery setup.
    
    Returns:
        String 'pong' to confirm Celery is working
    """
    return "pong"

@celery.task(name='process_scheduled_sms')
def process_scheduled_sms(scheduled_sms_id: int) -> Optional[Dict[str, Union[bool, str]]]:
    """Process a scheduled SMS by its ID.
    
    Args:
        scheduled_sms_id: ID of the scheduled SMS to process
        
    Returns:
        Dictionary containing success status and message details if successful,
        None if SMS not found
        
    Raises:
        Exception: If SMS processing fails
    """
    db = SessionLocal()
    try:
        scheduled_sms = db.query(ScheduledSMS).filter(
            ScheduledSMS.id == scheduled_sms_id
        ).first()
        
        if not scheduled_sms:
            logger.error(f"Scheduled SMS {scheduled_sms_id} not found")
            return None

        result = send_sms_via_twilio(
            to_number=scheduled_sms.to_number,
            message=scheduled_sms.message,
            business_id=scheduled_sms.business_id
        )

        # Update status based on send result
        scheduled_sms.status = "sent" if result.get("success") else "failed"
        scheduled_sms.sent_at = datetime.utcnow()
        db.commit()

        return result
        
    except Exception as e:
        logger.error(
            f"Error processing scheduled SMS {scheduled_sms_id}: {str(e)}",
            exc_info=True
        )
        raise
    finally:
        db.close()

@celery.task(name='schedule_sms')
def schedule_sms_task(
    to_number: str,
    message: str,
    business_id: int,
    scheduled_time: Optional[datetime] = None
) -> Dict[str, Union[bool, int]]:
    """Schedule an SMS to be sent.
    
    Args:
        to_number: Recipient's phone number
        message: SMS content to send
        business_id: ID of the business sending the SMS
        scheduled_time: When to send the SMS (None for immediate)
        
    Returns:
        Dictionary containing success status and scheduled SMS ID
        
    Raises:
        Exception: If SMS scheduling fails
    """
    db = SessionLocal()
    try:
        # Create scheduled SMS record
        scheduled_sms = ScheduledSMS(
            to_number=to_number,
            message=message,
            business_id=business_id,
            scheduled_time=scheduled_time or datetime.utcnow(),
            status="pending"
        )
        db.add(scheduled_sms)
        db.commit()
        db.refresh(scheduled_sms)

        # Send immediately if no future time specified
        current_time = datetime.utcnow()
        if not scheduled_time or scheduled_time <= current_time:
            process_scheduled_sms.delay(scheduled_sms.id)

        return {
            "success": True,
            "scheduled_sms_id": scheduled_sms.id
        }
        
    except Exception as e:
        logger.error(f"Error scheduling SMS: {str(e)}", exc_info=True)
        raise
    finally:
        db.close()