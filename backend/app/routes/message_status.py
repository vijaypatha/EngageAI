from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import Message, Customer, BusinessProfile
from app.schemas import ScheduledSMSOut
from pytz import timezone
import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/debug/{customer_id}")
def get_message_debug(customer_id: int, db: Session = Depends(get_db)):
    """Debug endpoint to check all messages for a customer"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    messages = db.query(Message).filter(
        Message.customer_id == customer_id,
        Message.message_type == 'scheduled'
    ).all()

    result = []
    for msg in messages:
        result.append({
            "id": msg.id,
            "content": msg.content,
            "status": msg.status,
            "scheduled_time": msg.scheduled_time.isoformat() if msg.scheduled_time else None,
            "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
            "source": msg.message_metadata.get('source', 'scheduled') if msg.message_metadata else 'scheduled'
        })

    return {
        "customer_id": customer_id,
        "messages": result
    }

@router.get("/scheduled/{customer_id}")
def get_scheduled_sms(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    messages = db.query(Message).options(
        joinedload(Message.business)
    ).filter(
        Message.customer_id == customer_id,
        Message.message_type == 'scheduled',
        Message.status == "scheduled",
        Message.scheduled_time > datetime.datetime.now(datetime.timezone.utc)
    ).all()

    if not messages:
        raise HTTPException(status_code=404, detail="No scheduled messages found")

    return [format_message_response(msg, customer) for msg in messages]

@router.get("/sent/{customer_id}")
def get_sent_sms(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    messages = db.query(Message).options(
        joinedload(Message.business)
    ).filter(
        Message.customer_id == customer_id,
        Message.message_type == 'scheduled',
        Message.status == "sent"
    ).all()

    if not messages:
        raise HTTPException(status_code=404, detail="No sent messages found")

    return [format_message_response(msg, customer) for msg in messages]

def format_message_response(message: Message, customer: Customer):
    business = message.business
    return {
        "id": message.id,
        "customer_id": message.customer_id,
        "business_id": message.business_id,
        "content": message.content,
        "status": message.status,
        "send_time": message.scheduled_time.isoformat() if message.scheduled_time else None,
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "source": message.message_metadata.get('source', 'scheduled') if message.message_metadata else 'scheduled',
        "is_hidden": message.is_hidden,
        "business_timezone": business.timezone if business else "UTC",
        "customer_timezone": customer.timezone if customer else None
    }

# 🔹 Pending messages for a specific customer
@router.get("/pending/{customer_id}")
def get_pending_sms(customer_id: int, db: Session = Depends(get_db)):
    messages = db.query(Message).filter(
        Message.customer_id == customer_id,
        Message.message_type == 'scheduled',
        Message.status == "pending_review"
    ).all()

    # Human-readable timing
    customer_tz = "America/Denver"  # TODO: Get from customer preferences
    tz = timezone(customer_tz)
    today = datetime.datetime.now(tz).date()

    response = []
    for msg in messages:
        local_dt = msg.scheduled_time.astimezone(tz)
        day_offset = (local_dt.date() - today).days
        formatted = local_dt.strftime(f"%A, %b %d (Day {day_offset}), %I:%M %p")

        response.append({
            "id": msg.id,
            "message": msg.content,
            "send_time": msg.scheduled_time,
            "formatted_timing": formatted,
            "status": msg.status
        })

    return response


# Alias routes for message-status
@router.get("/message-status/scheduled/{customer_id}")
def alias_scheduled(customer_id: int, db: Session = Depends(get_db)):
    return get_scheduled_sms(customer_id, db)

@router.get("/message-status/sent/{customer_id}")
def alias_sent(customer_id: int, db: Session = Depends(get_db)):
    return get_sent_sms(customer_id, db)