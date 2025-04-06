from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ScheduledSMS, Customer
from app.schemas import SMSCreate
from app.celery_tasks import schedule_sms_task
from app.utils import parse_sms_timing  # ✅ Required for roadmap parsing
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/schedule")
def schedule_sms(sms: SMSCreate, db: Session = Depends(get_db)):
    """
    Schedules a single SMS for sending immediately via Celery.
    """
    customer = db.query(Customer).filter(Customer.id == sms.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    sms_entry = ScheduledSMS(
        customer_id=sms.customer_id,
        business_id=customer.business_id,
        message=sms.message,
        status="scheduled"
    )
    db.add(sms_entry)
    db.commit()  # ✅ Must commit before Celery call

    logger.info(f"📤 SMS {sms_entry.id} scheduled immediately for {customer.phone}")

    schedule_sms_task.apply_async(args=[sms_entry.id])  # ✅ Kick off Celery task
    return {"message": f"SMS {sms_entry.id} scheduled for sending"}

@router.post("/schedule-roadmap")
def schedule_sms_roadmap(roadmap: list, customer_id: int, db: Session = Depends(get_db)):
    """
    Schedules a roadmap of SMS messages with send_time.
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer_timezone = getattr(customer, "timezone", "UTC")

    created_sms_ids = []

    for sms in roadmap:
        if "day" not in sms or "message" not in sms:
            continue  # Skip invalid items

        scheduled_time_utc = parse_sms_timing(sms["day"], customer_timezone)

        sms_entry = ScheduledSMS(
            customer_id=customer_id,
            business_id=customer.business_id,
            message=sms["message"],
            status="scheduled",
            send_time=scheduled_time_utc
        )
        db.add(sms_entry)
        db.flush()  # Get ID before full commit

        created_sms_ids.append(sms_entry.id)

    db.commit()

    for sms_id in created_sms_ids:
        schedule_sms_task.apply_async(args=[sms_id], eta=scheduled_time_utc)

    return {"message": f"{len(created_sms_ids)} SMS messages scheduled!"}
