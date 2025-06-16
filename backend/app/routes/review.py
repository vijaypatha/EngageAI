# backend/app/routes/review.py

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, select, func, case, and_, or_

# All necessary imports are consolidated here
from app.database import get_db
from app.models import (
    Customer, 
    Message,
    Engagement, 
    ConsentLog,
    CoPilotNudge,
    NudgeTypeEnum,
    NudgeStatusEnum,
    MessageTypeEnum,
    MessageStatusEnum
)
from pydantic import BaseModel

# --- Pydantic Models ---
# It's better to keep these in app/schemas.py, but for this file, they are defined here.
class InboxCustomerSummary(BaseModel):
    customer_id: int
    customer_name: Optional[str]
    phone: Optional[str]
    last_message_content: Optional[str]
    last_message_timestamp: Optional[datetime]
    unread_message_count: int
    opted_in: bool
    consent_status: str
    has_draft: bool
    has_opportunity: bool
    class Config: from_attributes = True

class PaginatedInboxSummaries(BaseModel):
    items: List[InboxCustomerSummary]
    total: int
    page: int
    size: int
    pages: int
    total_drafts: int
    total_opportunities: int
    total_unread: int

class CustomerBasicInfo(BaseModel):
    id: int
    customer_name: Optional[str]
    phone: Optional[str]
    class Config: from_attributes = True

class AutopilotMessage(BaseModel):
    id: int
    content: str
    scheduled_time: Optional[datetime]
    status: str # Using str to match MessageStatusEnum values
    customer: CustomerBasicInfo
    class Config: from_attributes = True


# --- Router Setup ---
logger = logging.getLogger(__name__)
router = APIRouter(
    #prefix="/review",
    tags=["review"]
)

@router.get("/inbox/summaries", response_model=PaginatedInboxSummaries)
def get_inbox_summaries(
    business_id: int = Query(..., description="The ID of the business to fetch inbox summaries for."),
    page: int = Query(1, ge=1, description="Page number for pagination."),
    size: int = Query(20, ge=1, le=100, description="Number of items per page."),
    db: Session = Depends(get_db)
):
    """
    PERFORMANCE REWRITE: This query is optimized to load the inbox list much faster.
    """
    logger.info(f"Fetching paginated inbox summaries for business_id={business_id}, page={page}, size={size}")
    offset = (page - 1) * size

    # Optimized subqueries for faster data aggregation
    last_msg_subquery = (
        select(Message.customer_id, func.max(Message.created_at).label("last_message_timestamp"))
        .filter(Message.business_id == business_id).group_by(Message.customer_id).subquery("last_msg_subquery")
    )
    unread_counts_subquery = (
        select(Customer.id.label("customer_id"), func.count(Message.id).label("unread_count"))
        .join(Message, Message.customer_id == Customer.id)
        .filter(
            Customer.business_id == business_id,
            Message.message_type == MessageTypeEnum.INBOUND.value,
            or_(Customer.last_read_at.is_(None), Message.created_at > Customer.last_read_at)
        ).group_by(Customer.id).subquery("unread_counts_subquery")
    )
    draft_flags_subquery = select(Engagement.customer_id).filter(Engagement.business_id == business_id, Engagement.status == MessageStatusEnum.PENDING_REVIEW.value).distinct().subquery()
    opportunity_flags_subquery = select(CoPilotNudge.customer_id).filter(CoPilotNudge.business_id == business_id, CoPilotNudge.nudge_type == NudgeTypeEnum.SENTIMENT_POSITIVE.value, CoPilotNudge.status == NudgeStatusEnum.ACTIVE.value).distinct().subquery()
    last_message_content_sq = select(
        Message.customer_id, Message.content,
        func.row_number().over(partition_by=Message.customer_id, order_by=Message.created_at.desc()).label("row_num")
    ).filter(Message.business_id == business_id).subquery()
    
    # Final optimized query to build the inbox summaries
    customer_summaries_query = (
        select(
            Customer,
            case((Customer.id.in_(select(draft_flags_subquery)), True), else_=False).label("has_draft"),
            case((Customer.id.in_(select(opportunity_flags_subquery)), True), else_=False).label("has_opportunity"),
            last_message_content_sq.c.content.label("last_message_content"),
            last_msg_subquery.c.last_message_timestamp,
            func.coalesce(unread_counts_subquery.c.unread_count, 0).label("unread_message_count")
        )
        .outerjoin(last_msg_subquery, Customer.id == last_msg_subquery.c.customer_id)
        .outerjoin(unread_counts_subquery, Customer.id == unread_counts_subquery.c.customer_id)
        .outerjoin(last_message_content_sq, and_(Customer.id == last_message_content_sq.c.customer_id, last_message_content_sq.c.row_num == 1))
        .filter(Customer.business_id == business_id)
        .order_by(desc(last_msg_subquery.c.last_message_timestamp).nulls_last())
        .limit(size).offset(offset)
    )

    results = db.execute(customer_summaries_query).all()
    total_count = db.query(Customer).filter(Customer.business_id == business_id).count()

    summaries = []
    for row in results:
        customer, has_draft, has_opportunity, last_message_content, last_message_timestamp, unread_count = row
        latest_consent = db.query(ConsentLog).filter(ConsentLog.customer_id == customer.id).order_by(desc(ConsentLog.replied_at)).first()
        summaries.append(InboxCustomerSummary(
            customer_id=customer.id, customer_name=customer.customer_name, phone=customer.phone,
            last_message_content=last_message_content, last_message_timestamp=last_message_timestamp,
            unread_message_count=unread_count,
            opted_in=latest_consent.status == "opted_in" if latest_consent else False,
            consent_status=latest_consent.status if latest_consent else "pending",
            has_draft=has_draft, has_opportunity=has_opportunity
        ))
    
    total_unread = db.query(func.sum(unread_counts_subquery.c.unread_count)).scalar() or 0
    total_drafts = db.query(func.count(draft_flags_subquery.c.customer_id)).scalar()
    total_opportunities = db.query(func.count(opportunity_flags_subquery.c.customer_id)).scalar()
    total_pages = (total_count + size - 1) // size if total_count > 0 else 0
    
    return PaginatedInboxSummaries(
        items=summaries, total=total_count, page=page, size=size, pages=total_pages,
        total_drafts=total_drafts, total_opportunities=total_opportunities, total_unread=int(total_unread)
    )

# --- CORRECTED & IMPLEMENTED /autopilot-plan endpoint ---
@router.get(
    "/autopilot-plan",
    response_model=List[AutopilotMessage],
    summary="Get Autopilot Scheduled Flight Plan"
)
def get_autopilot_plan(
    business_id: int = Query(..., description="The ID of the business for the plan."),
    db: Session = Depends(get_db)
):
    """
    Retrieves all future scheduled messages for a business.
    This endpoint is guaranteed to return a list, even if an error occurs,
    to prevent ResponseValidationError.
    """
    logger.info(f"Fetching Autopilot flight plan for business_id: {business_id}")
    
    # Get the current time in UTC for accurate future-time comparison
    now_utc = datetime.now(timezone.utc)
    
    try:
        # The query to find all relevant scheduled messages.
        # It joins the customer to include their name and sorts by the scheduled date.
        scheduled_messages = (
            db.query(Message)
            .options(joinedload(Message.customer))
            .filter(
                Message.business_id == business_id,
                Message.message_type == MessageTypeEnum.SCHEDULED,
                Message.status == MessageStatusEnum.SCHEDULED,
                Message.scheduled_time > now_utc
            )
            .order_by(Message.scheduled_time.asc())
            .all()
        )
        
        logger.info(f"Successfully found {len(scheduled_messages)} messages for business_id: {business_id}")
        
        # This is the successful path. It returns a list of ORM objects.
        # FastAPI will automatically serialize this into JSON based on the response_model.
        return scheduled_messages

    except Exception as e:
        # This block catches any unexpected database or other errors during the query.
        logger.error(
            f"A critical error occurred while fetching Autopilot plan for business_id {business_id}. Error: {e}",
            exc_info=True # Set to True to log the full stack trace for better debugging.
        )
        # It's crucial to re-raise an HTTPException here. This gives FastAPI a proper
        # JSON error response to send to the client and avoids the ResponseValidationError.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while fetching the scheduled flight plan."
        )

# --- Placeholder for /full-customer-history ---
@router.get("/full-customer-history", response_model=List[Dict[str, Any]])
def get_full_customer_history(business_id: int, db: Session = Depends(get_db)):
    # This endpoint is not implemented yet.
    logger.warning(f"Endpoint /full-customer-history called for business_id {business_id}, but it is not implemented.")
    # Returning an empty list to avoid breaking clients that might call this.
    return []
