# backend/app/routes/review.py
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from app.database import get_db
from app.models import (
    Customer, 
    Message, 
    Engagement, 
    ConsentLog,
    MessageTypeEnum, 
    MessageStatusEnum
)
# Note: Some schemas and services may become unused after this refactor.
# They are kept here for now if other functions still depend on them.
from app.services.stats_service import get_stats_for_business, calculate_reply_stats
from app.schemas import PaginatedInboxSummaries
from app.services import inbox_service

logger = logging.getLogger(__name__)

# The router prefix is set in main.py, so we define it without a prefix here.
router = APIRouter()

@router.get("/full-customer-history", response_model=List[Dict[str, Any]])
def get_full_customer_history(
    business_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """
    REFACTORED: Provides a definitive, chronologically sorted timeline of all messages 
    for all customers of a given business, establishing `messages` as the single source of truth.
    """
    logger.info(f"Fetching definitive customer history for business_id: {business_id}")

    # Step 1: Get all customers for the business.
    customers = db.query(Customer).filter(Customer.business_id == business_id).all()
    if not customers:
        return []

    customer_ids = [c.id for c in customers]
    customer_history_result = []

    # Step 2: Fetch all relevant messages for all customers of the business in one query.
    all_messages = (
        db.query(Message)
        .filter(
            Message.customer_id.in_(customer_ids),
            Message.is_hidden == False,
            Message.content.isnot(None),
            Message.content != ''
        )
        .order_by(Message.customer_id, Message.created_at)
        .all()
    )

    # Step 3: Efficiently fetch all pending AI drafts from the 'engagements' table.
    inbound_message_ids = [m.id for m in all_messages if m.message_type == MessageTypeEnum.INBOUND.value]
    
    pending_drafts_map = {}
    if inbound_message_ids:
        pending_drafts = db.query(
            Engagement.message_id,
            Engagement.ai_response,
            Engagement.id
        ).filter(
            Engagement.message_id.in_(inbound_message_ids),
            Engagement.status == 'pending_review',
            Engagement.ai_response.isnot(None)
        ).all()
        # Create a lookup map: {message_id: (ai_response, engagement_id)}
        pending_drafts_map = {msg_id: (ai_resp, eng_id) for msg_id, ai_resp, eng_id in pending_drafts}

    # Step 4: Group messages by customer.
    messages_by_customer: Dict[int, List[Dict[str, Any]]] = {}
    for msg in all_messages:
        if msg.customer_id not in messages_by_customer:
            messages_by_customer[msg.customer_id] = []
        
        message_entry = {
            "id": f"msg-{msg.id}",
            "type": msg.message_type,
            "content": msg.content,
            "status": msg.status,
            "sent_time": (msg.sent_at or msg.created_at).isoformat(),
            "customer_id": msg.customer_id,
        }

        # If it's an inbound message, attach the pending AI draft.
        if msg.message_type == MessageTypeEnum.INBOUND.value and msg.id in pending_drafts_map:
            ai_response_content, engagement_id = pending_drafts_map[msg.id]
            message_entry["ai_response"] = ai_response_content
            message_entry["ai_draft_id"] = engagement_id
        
        messages_by_customer[msg.customer_id].append(message_entry)

    # Step 5: Assemble the final list with customer metadata.
    for customer in customers:
        if customer.id in messages_by_customer:
            latest_consent = db.query(ConsentLog).filter(ConsentLog.customer_id == customer.id).order_by(desc(ConsentLog.replied_at)).first()
            
            customer_history_result.append({
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "phone": customer.phone,
                "opted_in": latest_consent.status == "opted_in" if latest_consent else False,
                "consent_status": latest_consent.status if latest_consent else "pending",
                "message_count": len(messages_by_customer[customer.id]),
                "messages": messages_by_customer[customer.id]
            })

    return customer_history_result


@router.get("/engagement-plan/{customer_id}")
def get_engagement_plan(customer_id: int, db: Session = Depends(get_db)):
    """
    REFACTORED: Gets the future-scheduled engagement plan for a customer.
    This now queries ONLY the `messages` table for `scheduled` messages.
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # The single source of truth for a scheduled plan is the Message table.
    scheduled_messages = db.query(Message).filter(
        Message.customer_id == customer_id,
        Message.status == MessageStatusEnum.SCHEDULED.value,
        Message.scheduled_time >= datetime.now(timezone.utc)
    ).order_by(Message.scheduled_time.asc()).all()

    # The concept of a separate "roadmap" vs "scheduled" is gone.
    # The frontend will now receive a clean list of what is truly scheduled.
    engagements = []
    for msg in scheduled_messages:
        engagements.append({
            "id": msg.id,
            "smsContent": msg.content,
            "status": msg.status,
            "send_datetime_utc": msg.scheduled_time.isoformat() if msg.scheduled_time else None,
            "source": msg.message_metadata.get('source', 'scheduled') if msg.message_metadata else 'scheduled'
        })

    return {
        "engagements": engagements,
        "customer_name": customer.customer_name # Added for context
    }


@router.get("/customer-replies", response_model=List[Dict[str, Any]])
def get_customer_replies(business_id: int = Query(...), db: Session = Depends(get_db)):
    """
    REFACTORED: Gets all customer replies for a business.
    This now queries the `messages` table for `inbound` messages, not the `engagements` table.
    """
    replies = (
        db.query(Message)
        .join(Customer, Message.customer_id == Customer.id)
        .filter(
            Message.business_id == business_id,
            Message.message_type == MessageTypeEnum.INBOUND.value,
            Message.is_hidden == False,
            Message.content.isnot(None),
            Message.content != ''
        )
        .order_by(Message.created_at.desc())
        .options(joinedload(Message.customer))
        .all()
    )

    result = []
    for message in replies:
        result.append({
            "id": message.id, # The Message ID is now the unique identifier for this event
            "customer_id": message.customer_id,
            "customer_name": message.customer.customer_name,
            "phone": message.customer.phone,
            "response": message.content, # The inbound message content is the reply
            "timestamp": message.created_at.isoformat(),
            "lifecycle_stage": message.customer.lifecycle_stage
        })
    return result


# NOTE: The following routes were not specified in the refactor plan.
# They are preserved from the original file but may need future refactoring 
# to be fully consistent with the new data model, especially the stats routes.

@router.get("/stats/{business_id}")
def get_stats(business_id: int, db: Session = Depends(get_db)):
    """API endpoint for getting message counts by status"""
    return get_stats_for_business(business_id, db)

@router.get("/reply-stats/{business_id}")
def get_reply_stats(business_id: int, db: Session = Depends(get_db)):
    """API endpoint for getting reply stats"""
    return calculate_reply_stats(business_id, db)

@router.get("/inbox/summaries", response_model=PaginatedInboxSummaries)
def get_inbox_summaries(
    business_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get paginated inbox summaries for a business.
    Includes customer info, last message snippet, timestamp, and unread count.
    """
    summaries, total_count = inbox_service.get_paginated_inbox_summaries(
        db=db, business_id=business_id, page=page, size=size
    )

    return {
        "items": summaries,
        "total": total_count,
        "page": page,
        "size": size,
        "pages": (total_count + size - 1) // size if size > 0 else 0
    }

# The other functions from the original file are removed as they are now obsolete
# due to the new, more efficient data fetching patterns above.