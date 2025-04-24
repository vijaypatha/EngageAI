from dotenv import load_dotenv
import os
import logging
from typing import Optional
from datetime import datetime

from app.services.twilio_sms_service import send_sms_via_twilio
from app.database import SessionLocal
from app.models import Message, Customer, BusinessProfile
from app.celery_app import celery_app as celery  # ✅ Uses correct broker + config

# Load environment variables
load_dotenv()

# Use existing Celery app (not a new one)
celery.conf.enable_utc = True
celery.conf.timezone = "UTC"

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@celery.task(bind=True, max_retries=3, default_retry_delay=60,  name="app.celery_tasks.schedule_sms_task",
    queue="celery")
def schedule_sms_task(self, message_id: int, roadmap_id: Optional[int] = None):
    """
    Celery task to send SMS by ID.
    Logs details and sends message via Twilio if time is reached.
    """
    db = SessionLocal()
    logger.info(f"[🔍 CELERY DB CHECK] Env: {os.getenv('DATABASE_URL')}")
    logger.info(f"[🚀 CELERY RUNNING] Task started for message_id={message_id}")

    try:
        message = db.query(Message).filter(
            Message.id == message_id,
            Message.message_type == 'scheduled'
        ).first()
        
        if not message:
            logger.error(f"[❌] Message ID {message_id} not found in DB.")
            return
        else:
            logger.info(f"[✅] Message ID {message_id} found with status: {message.status}")

        # 🚫 Skip execution if status is not scheduled
        if message.status != "scheduled":
            logger.info(f"[⏹] Message {message.id} skipped due to status: {message.status}")
            return
        
        # Link roadmap_id if available
        if roadmap_id:
            message.message_metadata = message.message_metadata or {}
            message.message_metadata['roadmap_id'] = roadmap_id
            db.commit()
            logger.info(f"[🧭 Message {message.id}] Linked to roadmap_id={roadmap_id}")

        if message.status == "sent":
            logger.info(f"[🛑] Message {message.id} already sent. Skipping to prevent duplicate.")
            return

        customer = db.query(Customer).filter(Customer.id == message.customer_id).first()
        if not customer:
            logger.error(f"[❌] No customer for Message ID {message_id}")
            return
        
        if not customer.opted_in:
            logger.warning(f"[🔒 Message {message.id}] Blocked: Customer {customer.id} has not opted in.")
            return

        # Log timing
        scheduled_time = message.scheduled_time.strftime('%Y-%m-%d %H:%M:%S')
        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

        logger.info(f"[📨 Message {message.id}] Scheduled for: {scheduled_time}")
        logger.info(f"[⏰ Message {message.id}] Current UTC time: {current_time}")
        logger.info(f"[👤 Message {message.id}] To: {customer.phone}")
        logger.info(f"[💬 Message {message.id}] Content: {message.content}")

        # Check time before sending
        if datetime.utcnow() >= message.scheduled_time.replace(tzinfo=None):
            business = db.query(BusinessProfile).filter(BusinessProfile.id == message.business_id).first()
            sid = send_sms_via_twilio(customer.phone, message.content, business)
            message.status = "sent"
            message.sent_at = datetime.utcnow()
            db.commit()
            logger.info(f"[✅ Message {message.id}] Sent! Twilio SID: {sid}")
        else:
            logger.warning(f"[⏳ Message {message.id}] Not time yet, skipping send.")

    except Exception as e:
        logger.exception(f"[🔥 Message {message_id}] Error: {str(e)}")
        raise self.retry(exc=e)

    finally:
        db.close()