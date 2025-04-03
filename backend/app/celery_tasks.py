from celery import Celery
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import logging
import os
import datetime
from sqlalchemy.orm import joinedload
from app.database import SessionLocal
from app.models import ScheduledSMS

# Load env vars
from dotenv import load_dotenv
load_dotenv()

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Setup Celery
celery = Celery("tasks", broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
celery.conf.enable_utc = True
celery.conf.timezone = 'UTC'

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def send_sms(self, sms_id: int):
    now_utc = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[SMS {sms_id}] 🚀 Task STARTED at {now_utc} UTC")
    
    db = SessionLocal()

    try:
        sms = db.query(ScheduledSMS)\
            .options(joinedload(ScheduledSMS.customer))\
            .filter(ScheduledSMS.id == sms_id)\
            .first()

        if not sms:
            logger.error(f"[SMS {sms_id}] ❌ SMS not found.")
            return

        if not sms.customer:
            logger.error(f"[SMS {sms_id}] ❌ No customer associated.")
            return

        phone = sms.customer.phone
        sms_text = sms.message
        send_time = sms.send_time.strftime("%Y-%m-%d %H:%M:%S")

        logger.info(f"[SMS {sms_id}] 📞 To: {phone}")
        logger.info(f"[SMS {sms_id}] 🕒 Scheduled Time (from DB): {send_time} UTC")
        logger.info(f"[SMS {sms_id}] 💬 Message: {sms_text}")
        print(f"[SMS {sms_id}] Inside send_sms: phone={phone}, text={sms_text}, time={now_utc}")

        message = client.messages.create(
            body=sms_text,
            from_=TWILIO_PHONE_NUMBER,
            to=phone
        )

        sms.status = "sent"
        db.commit()

        logger.info(f"[SMS {sms_id}] ✅ Sent successfully! Twilio SID: {message.sid}")
        print(f"[SMS {sms_id}] Twilio SID: {message.sid}")

    except TwilioRestException as e:
        logger.error(f"[SMS {sms_id}] ❌ Twilio error: {str(e)}")
        print(f"[SMS {sms_id}] Twilio Exception: {e}")
        raise self.retry(exc=e)

    except Exception as e:
        logger.error(f"[SMS {sms_id}] ❌ General error: {str(e)}")
        print(f"[SMS {sms_id}] General Exception: {e}")
        raise

    finally:
        db.close()
