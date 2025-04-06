from celery import Celery
from dotenv import load_dotenv
import os
import logging
from datetime import datetime

from app.services.twilio_sms_service import send_sms_via_twilio
from app.database import SessionLocal
from app.models import ScheduledSMS, Customer


# Load environment variables
load_dotenv()

# Configure Celery
celery = Celery(
    "tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
)

celery.conf.enable_utc = True
celery.conf.timezone = "UTC"

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def schedule_sms_task(self, scheduled_sms_id: int):
    """
    Celery task to send SMS by ID.
    Logs details and sends message via Twilio if time is reached.
    """
    db = SessionLocal()

    try:
        sms = db.query(ScheduledSMS).filter(ScheduledSMS.id == scheduled_sms_id).first()
        if not sms:
            logger.error(f"[❌] SMS ID {scheduled_sms_id} not found.")
            return
        
        if sms.status == "sent":
         logger.info(f"[🛑] SMS {sms.id} already sent. Skipping to prevent duplicate.")
         return

        customer = db.query(Customer).filter(Customer.id == sms.customer_id).first()
        if not customer:
            logger.error(f"[❌] No customer for SMS ID {scheduled_sms_id}")
            return

        # Log timing
        scheduled_time = sms.send_time.strftime('%Y-%m-%d %H:%M:%S')
        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

        logger.info(f"[📨 SMS {sms.id}] Scheduled for: {scheduled_time}")
        logger.info(f"[⏰ SMS {sms.id}] Current UTC time: {current_time}")
        logger.info(f"[👤 SMS {sms.id}] To: {customer.phone}")
        logger.info(f"[💬 SMS {sms.id}] Message: {sms.message}")

        # Check time before sending
        if datetime.utcnow() >= sms.send_time.replace(tzinfo=None):
            sid = send_sms_via_twilio(customer.phone, sms.message)
            sms.status = "sent"
            db.commit()
            logger.info(f"[✅ SMS {sms.id}] Sent! Twilio SID: {sid}")
        else:
            logger.warning(f"[⏳ SMS {sms.id}] Not time yet, skipping send.")

    except Exception as e:
        logger.exception(f"[🔥 SMS {scheduled_sms_id}] Error: {str(e)}")
        raise self.retry(exc=e)

    finally:
        db.close()
