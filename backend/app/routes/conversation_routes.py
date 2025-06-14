# backend/app/routes/conversation_routes.py

from datetime import datetime, timezone as dt_timezone
import logging
import traceback
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Request, status, Response, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, cast, Integer, text, func
import pytz
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from app.database import get_db
from app.models import (
    BusinessProfile,
    Engagement,
    Message,
    Conversation as ConversationModel,
    ConsentLog,
    Customer,
    CoPilotNudge,
    NudgeTypeEnum,
    NudgeStatusEnum,
    MessageTypeEnum,
    MessageStatusEnum
)

from app.services.ai_service import AIService
from app.services.consent_service import ConsentService
from app.config import settings
from app.services.twilio_service import TwilioService

from app.schemas import normalize_phone_number as normalize_phone, MessageCreateSchema, MessageResponse
import re

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Conversations"])


class CustomerDetailsResponse(BaseModel):
    id: int
    customer_name: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    interaction_history: Optional[str] = None
    pain_points: Optional[str] = None

    class Config:
        from_attributes = True

@router.get("/customers/{customer_id}/details", response_model=CustomerDetailsResponse, tags=["Customers"])
def get_customer_details(customer_id: int, db: Session = Depends(get_db)):
    """
    Fetches detailed information for a single customer, used by the Customer Intelligence Panel.
    """
    logger.info(f"Fetching details for customer_id={customer_id}")
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.put("/customers/{customer_id}/mark-as-read", status_code=status.HTTP_200_OK)
def mark_customer_conversation_as_read(
    customer_id: int,
    db: Session = Depends(get_db)
):
    """
    Updates the 'last_read_at' timestamp for a customer, which marks their conversation as read.
    The final URL will be /conversations/customers/{id}/mark-as-read
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    
    customer.last_read_at = datetime.now(dt_timezone.utc)
    try:
        db.commit()
        db.refresh(customer)
        logger.info(f"Customer {customer_id} conversation marked as read at {customer.last_read_at}.")
        return {"message": f"Conversation for customer {customer_id} marked as read."}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to mark as read for customer {customer_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not update customer read timestamp.")


@router.post("/customer/{customer_id}/send-message", response_model=MessageResponse)
async def send_message_from_inbox(
    customer_id: int,
    payload: MessageCreateSchema,
    db: Session = Depends(get_db)
):
    """
    Sends a message from the inbox and automatically handles appending a personalized
    opt-in consent request for new contacts.
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found for customer")

    message_to_send = payload.message
    is_first_message = customer.sms_opt_in_status == 'not_set'
    
    # Dynamic & Personalized Opt-in Logic
    if is_first_message:
        if business.sms_opt_in_message:
            opt_in_text = business.sms_opt_in_message
        else:
            representative_name = getattr(business, 'representative_name', business.business_name)
            business_name = business.business_name
            opt_in_text = (
                f"{representative_name} from {business_name} wants to stay in touch. "
                "Reply YES to subscribe. Msg&Data rates may apply. Reply STOP to unsubscribe."
            )
        
        message_to_send += f" {opt_in_text}"
        logger.info(f"Appending personalized opt-in text for new customer {customer_id}")

    conversation = db.query(ConversationModel).filter(
        ConversationModel.customer_id == customer.id,
        ConversationModel.business_id == business.id,
        ConversationModel.status == 'active'
    ).first()
    now_utc = datetime.now(dt_timezone.utc)
    if not conversation:
        conversation = ConversationModel(id=uuid.uuid4(), customer_id=customer.id, business_id=business.id, started_at=now_utc, last_message_at=now_utc, status='active')
        db.add(conversation)
        db.flush()

    db_message = Message(
        conversation_id=conversation.id, business_id=business.id, customer_id=customer.id,
        content=payload.message,
        message_type=MessageTypeEnum.OUTBOUND.value, status=MessageStatusEnum.QUEUED.value,
        created_at=now_utc, sent_at=None, 
        message_metadata={'source': 'manual_inbox_reply', 'opt_in_appended': is_first_message}
    )
    db.add(db_message)
    db.flush()
    twilio_service = TwilioService(db=db)
    try:
        sent_message_sid = await twilio_service.send_sms(
            to=customer.phone, message_body=message_to_send, business=business, 
            customer=customer, is_direct_reply=True
        )
        if sent_message_sid:
            db_message.status = MessageStatusEnum.SENT.value
            db_message.sent_at = datetime.now(dt_timezone.utc)
            db_message.message_metadata['twilio_sid'] = sent_message_sid
            if is_first_message:
                customer.sms_opt_in_status = 'pending'
        else:
            db_message.status = MessageStatusEnum.FAILED.value
            db.commit()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send message via Twilio, no SID received.")
    except Exception as e:
        db_message.status = MessageStatusEnum.FAILED.value
        db_message.message_metadata['error'] = str(e)
        db.commit()
        raise
    conversation.last_message_at = db_message.sent_at if db_message.sent_at else now_utc
    db.commit()
    return db_message


@router.get("/customer/{customer_id}", response_model=Dict[str, Any])
def get_conversation_history(customer_id: int, db: Session = Depends(get_db)):
    """
    Rewritten to provide a clean, non-duplicated timeline.
    It fetches all messages and then attaches the single latest AI draft to its parent inbound message.
    """
    logger.info(f"get_conversation_history: Fetching history for customer_id={customer_id}")
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
    all_messages_orm = db.query(Message).filter(
        Message.customer_id == customer_id,
        Message.is_hidden == False
    ).order_by(Message.created_at.asc()).all()

    timeline = []
    processed_msg_ids = set()
    for msg in all_messages_orm:
        if msg.id in processed_msg_ids:
            continue
        processed_msg_ids.add(msg.id)

        timeline_entry = {
            "id": msg.id,
            "type": msg.message_type,
            "content": msg.content,
            "timestamp": (msg.sent_at or msg.created_at).isoformat(),
            "status": msg.status,
            "ai_response": None,
            "ai_draft_id": None,
            "contextual_action": None,
            "appended_opt_in_prompt": msg.message_metadata.get('opt_in_appended', False) if isinstance(msg.message_metadata, dict) else False
        }
        timeline.append(timeline_entry)

    inbound_message_ids = [m['id'] for m in timeline if m["type"] == MessageTypeEnum.INBOUND.value]
    if inbound_message_ids:
        latest_engagement_sq = db.query(
            Engagement.message_id,
            func.max(Engagement.id).label('latest_id')
        ).filter(
            Engagement.message_id.in_(inbound_message_ids),
            Engagement.status == MessageStatusEnum.PENDING_REVIEW.value
        ).group_by(Engagement.message_id).subquery()

        latest_drafts = db.query(Engagement).join(
            latest_engagement_sq,
            Engagement.id == latest_engagement_sq.c.latest_id
        ).all()

        drafts_map = {draft.message_id: draft for draft in latest_drafts}

        for entry in timeline:
            if entry["type"] == MessageTypeEnum.INBOUND.value and entry["id"] in drafts_map:
                draft = drafts_map[entry["id"]]
                entry["ai_response"] = draft.ai_response
                entry["ai_draft_id"] = draft.id

    logger.info(f"get_conversation_history: Returning {len(timeline)} history items for customer_id={customer_id}")
    return {
        "customer": { "id": customer.id, "name": customer.customer_name, "phone": customer.phone },
        "messages": timeline
    }


class ManualReplyInput(BaseModel):
    message: str

@router.post("/customer/{customer_id}/reply")
def send_manual_reply(customer_id: int, payload: ManualReplyInput, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        logger.error(f"send_manual_reply: Customer {customer_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    if not customer.business_id:
        logger.error(f"send_manual_reply: Customer {customer_id} does not have a business_id.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Customer is not associated with a business.")

    logger.info(f"send_manual_reply: Initiated for customer_id={customer_id}, business_id={customer.business_id}")
    now_utc = datetime.now(pytz.UTC)

    conversation = db.query(ConversationModel).filter(
        ConversationModel.customer_id == customer.id,
        ConversationModel.business_id == customer.business_id,
        ConversationModel.status == 'active'
    ).first()

    if not conversation:
        logger.info(f"send_manual_reply: No active conversation found. Creating new one.")
        conversation = ConversationModel(
            id=uuid.uuid4(),
            customer_id=customer.id,
            business_id=customer.business_id,
            started_at=now_utc,
            last_message_at=now_utc,
            status='active'
        )
        db.add(conversation)
        db.flush()
    else:
        conversation.last_message_at = now_utc

    message_record = Message(
        conversation_id=conversation.id,
        customer_id=customer.id,
        business_id=customer.business_id,
        content=payload.message,
        message_type=MessageTypeEnum.SCHEDULED.value,
        status=MessageStatusEnum.SCHEDULED.value,
        scheduled_time=now_utc,
        message_metadata={'source': 'manual_reply_inbox'}
    )
    db.add(message_record)
    db.flush()

    task_id_str = None
    try:
        eta_value = message_record.scheduled_time
        if not isinstance(eta_value, datetime):
            eta_value = datetime.fromisoformat(str(eta_value))
        
        if eta_value.tzinfo is None:
            eta_value = pytz.utc.localize(eta_value)
        else:
            eta_value = eta_value.astimezone(pytz.utc)
        
        if eta_value < datetime.now(pytz.utc):
            logger.warning(f"ETA for message {message_record.id} is in the past: {eta_value.isoformat()}.")

        logger.info(f"Attempting to schedule Celery task for Message.id={message_record.id}, ETA='{eta_value.isoformat()}'")
        
        from app.celery_tasks import process_scheduled_message_task
        task_result = process_scheduled_message_task.apply_async(
            args=[message_record.id],
            eta=eta_value
        )
        task_id_str = task_result.id
        
        if not isinstance(message_record.message_metadata, dict):
            message_record.message_metadata = {}
        message_record.message_metadata['celery_task_id'] = task_id_str
        logger.info(f"Celery task successfully queued. Task ID: {task_id_str} for Message.id: {message_record.id}")

    except Exception as e:
        logger.error(f"Failed to schedule task via Celery for Message.id: {message_record.id}. Exception: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to add message to scheduling queue. Error: {str(e)}")

    new_engagement = Engagement(
        customer_id=customer.id,
        message_id=message_record.id,
        response=None,
        ai_response=payload.message,
        status=MessageStatusEnum.PROCESSING_SEND.value,
        sent_at=None,
        business_id=customer.business_id,
        created_at=now_utc
    )
    db.add(new_engagement)
    logger.info(f"send_manual_reply: Created Engagement record linked to message_record.id={message_record.id}")

    try:
        db.commit()
        db.refresh(new_engagement)
        logger.info(f"Database commit successful. Message_id={message_record.id}, New Engagement_id={new_engagement.id}")
    except Exception as e:
        db.rollback()
        logger.error(f"send_manual_reply: Database commit error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save reply to database.")

    return {
        "status": "success",
        "message": "Reply submitted for sending.",
        "message_id": message_record.id,
        "engagement_id": new_engagement.id,
        "engagement_status": new_engagement.status
    }