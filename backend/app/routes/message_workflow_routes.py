from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from app.database import get_db
from app.models import Message, Customer, BusinessProfile, MessageTypeEnum, MessageStatusEnum # Added Enums
# from app.schemas import ScheduledSMSOut # REMOVED THIS IMPORT
from app.schemas import MessageRead # Import MessageRead if you want to use it as response_model
from typing import List
from enum import Enum

from pytz import timezone # This import was in your file but not used, keeping for now.
import datetime # Use this for datetime.datetime.now and datetime.timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["Message Workflow"], # Added a tag for better OpenAPI docs
)

# Helper function to format message response (can be replaced by Pydantic model)
def format_message_response_dict(message: Message, customer: Customer) -> dict:
    business = message.business # Assumes Message.business relationship is loaded
    return {
        "id": message.id,
        "customer_id": message.customer_id,
        "business_id": message.business_id,
        "content": message.content,
        "status": message.status.value if isinstance(message.status, Enum) else message.status,
        "message_type": message.message_type.value if isinstance(message.message_type, Enum) else message.message_type,
        "scheduled_send_at": message.scheduled_send_at.isoformat() if message.scheduled_send_at else None, # CHANGED from scheduled_time
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "source": message.message_metadata.get('source', 'unknown') if message.message_metadata else 'unknown', # Added default
        "is_hidden": message.is_hidden,
        "business_timezone": business.timezone if business else "UTC", # Ensure business is loaded
        "customer_timezone": customer.timezone if customer else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "updated_at": message.updated_at.isoformat() if message.updated_at else None,
    }

@router.get("/debug/{customer_id}", summary="Debug: Get All Scheduled-Type Messages for Customer")
def get_message_debug(customer_id: int, db: Session = Depends(get_db)):
    """Debug endpoint to check all messages marked as 'scheduled_message' type for a customer, regardless of status."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    messages = db.query(Message).filter(
        Message.customer_id == customer_id,
        Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE # Use Enum
    ).order_by(desc(Message.scheduled_send_at)).all() # Order by scheduled time

    result = []
    for msg in messages:
        result.append({
            "id": msg.id,
            "content": msg.content,
            "status": msg.status.value if isinstance(msg.status, Enum) else msg.status,
            "message_type": msg.message_type.value if isinstance(msg.message_type, Enum) else msg.message_type,
            "scheduled_send_at": msg.scheduled_send_at.isoformat() if msg.scheduled_send_at else None, # CHANGED
            "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
            "source": msg.message_metadata.get('source', 'unknown') if msg.message_metadata else 'unknown',
            "created_at": msg.created_at.isoformat(),
            "updated_at": msg.updated_at.isoformat()
        })

    return {
        "customer_id": customer_id,
        "customer_name": customer.customer_name,
        "messages_debug": result
    }

@router.get("/scheduled/{customer_id}", summary="Get Upcoming Scheduled Messages for Customer", response_model=List[MessageRead])
def get_scheduled_sms(customer_id: int, db: Session = Depends(get_db)):
    """Retrieve upcoming messages of type 'scheduled_message' with status 'scheduled' for a customer."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Ensure datetime.timezone.utc is used correctly.
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    messages = db.query(Message).options(
        joinedload(Message.business), # Eager load business for timezone in formatting
        # joinedload(Message.customer) # Customer is already fetched
    ).filter(
        Message.customer_id == customer_id,
        Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE, # Use Enum
        Message.status == MessageStatusEnum.SCHEDULED,             # Use Enum
        Message.scheduled_send_at > now_utc # Compare with timezone-aware now_utc
    ).order_by(Message.scheduled_send_at).all()

    if not messages:
        # Return empty list instead of 404 for "no scheduled messages"
        logger.info(f"No upcoming scheduled messages found for customer_id: {customer_id}")
        return []

    # FastAPI will automatically serialize using MessageRead due to response_model
    return messages

@router.get("/sent/{customer_id}", summary="Get Sent Scheduled-Type Messages for Customer", response_model=List[MessageRead])
def get_sent_sms(customer_id: int, db: Session = Depends(get_db)):
    """Retrieve messages of type 'scheduled_message' with status 'sent' for a customer."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    messages = db.query(Message).options(
        joinedload(Message.business),
        # joinedload(Message.customer)
    ).filter(
        Message.customer_id == customer_id,
        Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE, # Use Enum
        Message.status == MessageStatusEnum.SENT                     # Use Enum
    ).order_by(desc(Message.sent_at)).all()

    if not messages:
        logger.info(f"No sent 'scheduled_message' type messages found for customer_id: {customer_id}")
        return []

    return messages


@router.get("/pending-review/{customer_id}", summary="Get Scheduled-Type Messages Pending Review for Customer", response_model=List[MessageRead])
def get_pending_review_sms(customer_id: int, db: Session = Depends(get_db)):
    """Retrieve messages of type 'scheduled_message' with status 'pending_review' for a customer."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    messages = db.query(Message).options(
        joinedload(Message.business),
        # joinedload(Message.customer)
    ).filter(
        Message.customer_id == customer_id,
        Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE, # Use Enum
        Message.status == MessageStatusEnum.PENDING_REVIEW         # Use Enum
    ).order_by(desc(Message.created_at)).all() # Or order_by(Message.scheduled_send_at)
    
    if not messages:
        logger.info(f"No 'scheduled_message' type messages pending review for customer_id: {customer_id}")
        return []
        
    # The response_model=List[MessageRead] will handle formatting.
    # The old formatted response with human-readable timing can be done on the frontend if needed.
    return messages


# Alias routes for message-status (kept for compatibility if frontend uses them)
@router.get("/message-status/scheduled/{customer_id}", deprecated=True, summary="DEPRECATED: Use /scheduled/{customer_id}", response_model=List[MessageRead])
def alias_scheduled(customer_id: int, db: Session = Depends(get_db)):
    logger.warning("Deprecated route /message-status/scheduled/{customer_id} called. Use /message-workflow/scheduled/{customer_id}.")
    return get_scheduled_sms(customer_id, db)

@router.get("/message-status/sent/{customer_id}", deprecated=True, summary="DEPRECATED: Use /sent/{customer_id}", response_model=List[MessageRead])
def alias_sent(customer_id: int, db: Session = Depends(get_db)):
    logger.warning("Deprecated route /message-status/sent/{customer_id} called. Use /message-workflow/sent/{customer_id}.")
    return get_sent_sms(customer_id, db)