from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Message, Customer, Conversation
from app.schemas import SMSCreate
from app.celery_tasks import schedule_sms_task
from app.utils import parse_sms_timing
import logging
from datetime import datetime, timezone, timedelta
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)

def has_recent_duplicate(db: Session, customer_id: int, content: str, within_minutes: int = 1) -> bool:
    """Check if the same message was scheduled for this customer within the last X minutes"""
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=within_minutes)
    
    duplicate_count = db.query(Message).filter(
        Message.customer_id == customer_id,
        Message.content == content,
        Message.created_at >= cutoff_time,
        Message.message_type == 'scheduled'
    ).count()
    
    return duplicate_count > 0

@router.post("/schedule")
def schedule_sms(sms: SMSCreate, db: Session = Depends(get_db)):
    """
    Schedules a single SMS for sending immediately via Celery.
    """
    # Check for recent duplicates
    if has_recent_duplicate(db, sms.customer_id, sms.message):
        raise HTTPException(
            status_code=400, 
            detail="A similar message was scheduled for this customer in the last 5 minutes"
        )

    customer = db.query(Customer).filter(Customer.id == sms.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Handle scheduled time
    if sms.send_time:
        try:
            scheduled_time = datetime.fromisoformat(sms.send_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datetime format. Use ISO format (e.g., 2025-04-24T10:00:00Z)")
    else:
        scheduled_time = datetime.now(timezone.utc)

    # Create or get conversation
    conversation = db.query(Conversation).filter(
        Conversation.customer_id == customer.id,
        Conversation.business_id == customer.business_id,
        Conversation.status == 'active'
    ).first()
    
    if not conversation:
        conversation = Conversation(
            id=uuid.uuid4(),
            customer_id=customer.id,
            business_id=customer.business_id,
            started_at=datetime.now(timezone.utc),
            last_message_at=datetime.now(timezone.utc),
            status='active'
        )
        db.add(conversation)
        db.flush()

    message = Message(
        conversation_id=conversation.id,
        customer_id=sms.customer_id,
        business_id=customer.business_id,
        content=sms.message,
        message_type='scheduled',
        status="scheduled",
        scheduled_time=scheduled_time,
        message_metadata={
            'source': 'scheduled'
        }
    )
    db.add(message)
    db.commit()

    # Log message details
    logger.info(f"Created message: id={message.id}, status={message.status}, type={message.message_type}, scheduled_time={scheduled_time}")

    schedule_sms_task.apply_async(args=[message.id], eta=scheduled_time)
    return {"message": f"Message {message.id} scheduled for sending"}

@router.post("/schedule-roadmap")
def schedule_sms_roadmap(roadmap: list, customer_id: int, db: Session = Depends(get_db)):
    """
    Schedules a roadmap of SMS messages with scheduled_time.
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer_timezone = getattr(customer, "timezone", "UTC")

    # Create or get conversation
    conversation = db.query(Conversation).filter(
        Conversation.customer_id == customer.id,
        Conversation.business_id == customer.business_id,
        Conversation.status == 'active'
    ).first()
    
    if not conversation:
        conversation = Conversation(
            id=uuid.uuid4(),
            customer_id=customer.id,
            business_id=customer.business_id,
            started_at=datetime.now(timezone.utc),
            last_message_at=datetime.now(timezone.utc),
            status='active'
        )
        db.add(conversation)
        db.flush()

    created_message_ids = []

    for sms in roadmap:
        if "day" not in sms or "message" not in sms:
            continue  # Skip invalid items

        scheduled_time_utc = parse_sms_timing(sms["day"], customer_timezone)

        message = Message(
            conversation_id=conversation.id,
            customer_id=customer_id,
            business_id=customer.business_id,
            content=sms["message"],
            message_type='scheduled',
            status="scheduled",
            scheduled_time=scheduled_time_utc
        )
        db.add(message)
        db.flush()

        created_message_ids.append(message.id)

    db.commit()

    for message_id in created_message_ids:
        schedule_sms_task.apply_async(args=[message_id], eta=scheduled_time_utc)

    return {"message": f"{len(created_message_ids)} messages scheduled!"}
