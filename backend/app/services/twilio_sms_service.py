from twilio.rest import Client
from app.models import Message, Customer, BusinessProfile
from app.database import SessionLocal
import os
import logging
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_sms_via_twilio(to, message, business):
    """
    Sends an SMS message via Twilio, using the business's assigned number if available.
    Falls back to the default TWILIO_PHONE_NUMBER from environment if not set.
    """
    client = Client(os.getenv("TWILIO_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    from_number = business.twilio_number or os.getenv("TWILIO_PHONE_NUMBER")

    try:
        twilio_msg = client.messages.create(
            to=to,
            from_=from_number,
            body=message
        )
        logger.info(f"📤 Sent SMS to {to} from {from_number}. SID: {twilio_msg.sid}")
        return twilio_msg.sid
    except Exception as e:
        logger.exception(f"❌ Failed to send SMS to {to} from {from_number}: {e}")
        return None

def send_sms_by_id(message_id: int):
    """
    Looks up a message by ID, sends it via Twilio, and marks it as sent.
    Called from Celery or direct trigger.
    """
    db = SessionLocal()
    try:
        message = db.query(Message).filter(
            Message.id == message_id,
            Message.message_type == 'scheduled'
        ).first()
        
        if not message:
            logger.error(f"❌ Message ID {message_id} not found.")
            return

        customer = db.query(Customer).filter(Customer.id == message.customer_id).first()
        if not customer or not customer.phone:
            logger.error(f"❌ Customer not found or missing phone for Message ID {message_id}")
            return

        business = db.query(BusinessProfile).filter(BusinessProfile.id == message.business_id).first()
        if not business:
            logger.error(f"❌ Business not found for Message ID {message_id}")
            return

        # 🕒 Check time before sending
        now_utc = datetime.now(timezone.utc)
        if message.scheduled_time and message.scheduled_time > now_utc:
            logger.info(f"⏱️ Not time yet to send Message ID {message_id}. Scheduled for {message.scheduled_time}, now is {now_utc}")
            return

        sid = send_sms_via_twilio(customer.phone, message.content, business)
        if sid:
            message.status = "sent"
            message.sent_at = now_utc
            db.commit()
            logger.info(f"✅ Message status updated to 'sent' for Message ID {message_id}")
        else:
            logger.error(f"❌ Message sending failed for Message ID {message_id}")

    except Exception as e:
        logger.exception(f"❌ Error sending Message ID {message_id}: {str(e)}")
    finally:
        db.close()
