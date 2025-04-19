from twilio.rest import Client
import os
from datetime import datetime
from app.database import SessionLocal
from app.models import ConsentLog, Customer, BusinessProfile

def send_double_optin_sms(customer_id: int):
    db = SessionLocal()
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()

    if not customer or not business:
        raise ValueError("Customer or Business not found")

    message_body = (
        f"Hi {customer.customer_name} — {business.representative_name} from {business.business_name} "
        "would love to send you helpful updates, tips, or reminders by SMS.\n"
        "Reply YES to opt in. Reply STOP to unsubscribe.\nStandard message rates may apply."
    )

    client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    from_number = business.twilio_number  # Assumes already assigned
    to_number = customer.phone

    if not from_number:
        raise ValueError(f"Missing Twilio number for business {business.id}. Cannot send SMS.")

    sms = client.messages.create(
        body=message_body,
        from_=from_number,
        to=to_number
    )

    # Log that opt-in was sent
    db.add(ConsentLog(
        customer_id=customer.id,
        business_id=business.id,
        method="double_opt_in",
        message_sid=sms.sid,
        phone_number=to_number,
        status="pending",
        sent_at=datetime.utcnow()
    ))
    db.commit()
    db.close()