# backend/app/routes/review.py

import logging
from typing import List, Dict, Any
from datetime import datetime
import pytz

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
from app.schemas import PaginatedInboxSummaries # Ensure PaginatedInboxSummaries is imported
from app.services import inbox_service # Import the inbox_service module
from app.services.stats_service import get_stats_for_business, calculate_reply_stats

logger = logging.getLogger(__name__)
router = APIRouter(tags=["review"])


@router.get("/inbox/summaries", response_model=PaginatedInboxSummaries)
def get_inbox_summaries(
    business_id: int = Query(..., description="The ID of the business to fetch inbox summaries for."),
    page: int = Query(1, ge=1, description="Page number for pagination."),
    size: int = Query(20, ge=1, le=100, description="Number of items per page."),
    db: Session = Depends(get_db)
):
    """
    Fetches paginated inbox summaries for a given business.
    This endpoint is designed to power the left-hand conversation list in the Nudge Inbox.
    It includes last message content, timestamp, and unread message count from the backend.
    """
    logger.info(f"Fetching paginated inbox summaries for business_id={business_id}, page={page}, size={size}")
    
    # Use the service to get the paginated data
    summaries, total_count = inbox_service.get_paginated_inbox_summaries(
        db=db,
        business_id=business_id,
        page=page,
        size=size
    )
    
    # Calculate total pages
    total_pages = (total_count + size - 1) // size if total_count > 0 else 0
    
    logger.info(f"Returning {len(summaries)} summaries (total {total_count}) for business_id={business_id}.")
    return PaginatedInboxSummaries(
        items=summaries,
        total=total_count,
        page=page,
        size=size,
        pages=total_pages
    )


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
    customers = db.query(Customer).filter(Customer.business_id == business_id).all()
    if not customers:
        return []

    customer_ids = [c.id for c in customers]
    customer_history_result = []

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

    inbound_message_ids = [m.id for m in all_messages if m.message_type == MessageTypeEnum.INBOUND.value]
    
    pending_drafts_map = {}
    if inbound_message_ids:
        pending_drafts = db.query(
            Engagement.message_id,
            Engagement.ai_response,
            Engagement.id
        ).filter(
            Engagement.message_id.in_(inbound_message_ids),
            Engagement.status == MessageStatusEnum.PENDING_REVIEW.value, # Use enum value
            Engagement.ai_response.isnot(None)
        ).all()
        pending_drafts_map = {msg_id: (ai_resp, eng_id) for msg_id, ai_resp, eng_id in pending_drafts}

    messages_by_customer: Dict[int, List[Dict[str, Any]]] = {}
    for msg in all_messages:
        if msg.customer_id not in messages_by_customer:
            messages_by_customer[msg.customer_id] = []
        
        timestamp = msg.sent_at or msg.created_at
        message_entry = {
            "id": f"msg-{msg.id}",
            "type": msg.message_type,
            "content": msg.content,
            "status": msg.status,
            "sent_time": timestamp.isoformat() if timestamp else None,
            "customer_id": msg.customer_id,
        }

        if msg.message_type == MessageTypeEnum.INBOUND.value and msg.id in pending_drafts_map:
            ai_response_content, engagement_id = pending_drafts_map[msg.id]
            message_entry["ai_response"] = ai_response_content
            message_entry["ai_draft_id"] = engagement_id
        
        messages_by_customer[msg.customer_id].append(message_entry)

    for customer in customers:
        if customer.id in messages_by_customer:
            latest_consent = db.query(ConsentLog).filter(ConsentLog.customer_id == customer.id).order_by(desc(ConsentLog.replied_at)).first()
            
            customer_history_result.append({
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "phone": customer.phone,
                "opted_in": latest_consent.status == "opted_in" if latest_consent else False,
                "consent_status": latest_consent.status if latest_consent else "pending",
                "consent_updated": latest_consent.replied_at.isoformat() if latest_consent and latest_consent.replied_at else None,
                "message_count": len(messages_by_customer[customer.id]),
                "messages": messages_by_customer[customer.id]
            })

    return customer_history_result