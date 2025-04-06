from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ScheduledSMS
from pytz import timezone
import datetime

router = APIRouter()

# 🔹 Scheduled messages
@router.get("/scheduled/{customer_id}")
def get_scheduled_sms(customer_id: int, db: Session = Depends(get_db)):
    return db.query(ScheduledSMS).filter(
        ScheduledSMS.customer_id == customer_id,
        ScheduledSMS.status == "scheduled"
    ).all()

# 🔹 Sent messages
@router.get("/sent/{customer_id}")
def get_sent_sms(customer_id: int, db: Session = Depends(get_db)):
    return db.query(ScheduledSMS).filter(
        ScheduledSMS.customer_id == customer_id,
        ScheduledSMS.status == "sent"
    ).all()

# 🔹 Pending messages for a specific customer
@router.get("/pending/{customer_id}")
def get_pending_sms(customer_id: int, db: Session = Depends(get_db)):
    sms_list = db.query(ScheduledSMS).filter(
        ScheduledSMS.customer_id == customer_id,
        ScheduledSMS.status == "pending_review"
    ).all()

    # Human-readable timing
    customer_tz = "America/Denver"
    tz = timezone(customer_tz)
    today = datetime.datetime.now(tz).date()

    response = []
    for sms in sms_list:
        local_dt = sms.send_time.astimezone(tz)
        day_offset = (local_dt.date() - today).days
        formatted = local_dt.strftime(f"%A, %b %d (Day {day_offset}), %I:%M %p")

        response.append({
            "id": sms.id,
            "message": sms.message,
            "send_time": sms.send_time,
            "formatted_timing": formatted,
            "status": sms.status
        })

    return response
