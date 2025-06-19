# backend/app/routes/review.py

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
# The main 'func' object is used to call DB functions in a dialect-agnostic way.
from sqlalchemy import desc, select, func, case, and_, or_, String
# JSONB and aggregate_order_by are still needed for type casting and ordering within the aggregation.
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by
# REMOVED the direct import of jsonb_build_object and jsonb_agg


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
    MessageStatusEnum,
    OptInStatus
)
from pydantic import BaseModel, Field


# --- Pydantic Models for this Route's Responses ---

class InboxNudge(BaseModel):
    type: str = Field(..., description="The type of nudge (e.g., 'draft', 'opportunity').")
    text: str = Field(..., description="The display text for the nudge.")
    class Config: from_attributes = True

class InboxCustomerSummary(BaseModel):
    customer_id: int
    customer_name: Optional[str]
    phone: Optional[str]
    last_message_content: Optional[str]
    last_message_timestamp: Optional[datetime]
    unread_message_count: int
    opted_in: bool
    consent_status: str
    active_nudges: List[InboxNudge] = []

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
    status: str
    customer: CustomerBasicInfo
    class Config: from_attributes = True


# --- API Router Setup ---
logger = logging.getLogger(__name__)
router = APIRouter(
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
    This optimized query loads the inbox list much faster and includes a list of active "nudges"
    (such as AI drafts and opportunities) for each customer conversation.
    """
    logger.info(f"Fetching V2 paginated inbox summaries for business_id={business_id}, page={page}, size={size}")
    offset = (page - 1) * size

    # Subquery to find the latest AI draft for each customer.
    latest_draft_subquery = (
        select(
            Engagement.customer_id,
            func.max(Engagement.id).label("latest_engagement_id")
        )
        .filter(
            Engagement.business_id == business_id,
            Engagement.status == MessageStatusEnum.PENDING_REVIEW.value,
            Engagement.ai_response.isnot(None)
        ).group_by(Engagement.customer_id).subquery("latest_drafts")
    )

    # Subquery to get all active nudges (e.g., opportunities) and aggregate them into a JSON array.
    # FIX: Use func.jsonb_agg and func.jsonb_build_object instead of direct imports.
    active_nudges_subquery = (
        select(
            CoPilotNudge.customer_id,
            func.jsonb_agg(
                aggregate_order_by(
                    func.jsonb_build_object(
                        'type', CoPilotNudge.nudge_type,
                        'text', CoPilotNudge.ai_suggestion
                    ),
                    CoPilotNudge.created_at.desc()
                )
            ).label("nudges")
        )
        .filter(
            CoPilotNudge.business_id == business_id,
            CoPilotNudge.status == NudgeStatusEnum.ACTIVE.value,
            CoPilotNudge.customer_id.isnot(None)
        ).group_by(CoPilotNudge.customer_id).subquery("active_nudges")
    )

    # Subqueries for unread counts and last message content/timestamp.
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
    last_message_content_sq = select(
        Message.customer_id, Message.content,
        func.row_number().over(partition_by=Message.customer_id, order_by=Message.created_at.desc()).label("row_num")
    ).filter(Message.business_id == business_id).subquery()

    # Main Query: Joins Customer data with all the pre-aggregated subquery results.
    customer_summaries_query = (
        select(
            Customer,
            last_message_content_sq.c.content.label("last_message_content"),
            last_msg_subquery.c.last_message_timestamp,
            func.coalesce(unread_counts_subquery.c.unread_count, 0).label("unread_message_count"),
            Engagement.ai_response.label("draft_text"),
            active_nudges_subquery.c.nudges.label("opportunity_nudges")
        )
        .outerjoin(last_msg_subquery, Customer.id == last_msg_subquery.c.customer_id)
        .outerjoin(unread_counts_subquery, Customer.id == unread_counts_subquery.c.customer_id)
        .outerjoin(last_message_content_sq, and_(Customer.id == last_message_content_sq.c.customer_id, last_message_content_sq.c.row_num == 1))
        .outerjoin(latest_draft_subquery, Customer.id == latest_draft_subquery.c.customer_id)
        .outerjoin(Engagement, Engagement.id == latest_draft_subquery.c.latest_engagement_id)
        .outerjoin(active_nudges_subquery, Customer.id == active_nudges_subquery.c.customer_id)
        .filter(Customer.business_id == business_id)
        .order_by(desc(func.coalesce(unread_counts_subquery.c.unread_count, 0)), desc(last_msg_subquery.c.last_message_timestamp).nulls_last())
        .limit(size).offset(offset)
    )

    results = db.execute(customer_summaries_query).all()
    total_count = db.query(Customer).filter(Customer.business_id == business_id).count()

    # Process results into the final Pydantic schema for the response.
    summaries = []
    for row in results:
        customer, last_message_content, last_message_timestamp, unread_count, draft_text, opportunity_nudges = row

        active_nudges_list = []
        if draft_text:
            active_nudges_list.append(InboxNudge(type="draft", text=draft_text))
        if opportunity_nudges:
            for nudge in opportunity_nudges:
                 active_nudges_list.append(InboxNudge(type=nudge.get('type', 'opportunity'), text=nudge.get('text', '')))

        latest_consent = db.query(ConsentLog).filter(ConsentLog.customer_id == customer.id).order_by(desc(ConsentLog.replied_at)).first()

        summaries.append(InboxCustomerSummary(
            customer_id=customer.id, customer_name=customer.customer_name, phone=customer.phone,
            last_message_content=last_message_content, last_message_timestamp=last_message_timestamp,
            unread_message_count=unread_count,
            opted_in=latest_consent.status == "opted_in" if latest_consent else False,
            consent_status=latest_consent.status if latest_consent else OptInStatus.NOT_SET.value,
            active_nudges=active_nudges_list
        ))

    # Calculate overall stats for pagination and filter bar counts.
    total_unread = db.query(func.sum(unread_counts_subquery.c.unread_count)).scalar() or 0
    total_drafts = db.query(func.count(latest_draft_subquery.c.customer_id)).scalar()
    total_opportunities = db.query(CoPilotNudge.id).filter(CoPilotNudge.business_id == business_id, CoPilotNudge.status == NudgeStatusEnum.ACTIVE, CoPilotNudge.customer_id.isnot(None)).count()
    total_pages = (total_count + size - 1) // size if total_count > 0 else 0

    return PaginatedInboxSummaries(
        items=summaries, total=total_count, page=page, size=size, pages=total_pages,
        total_drafts=total_drafts, total_opportunities=total_opportunities, total_unread=int(total_unread)
    )

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
    Retrieves all future scheduled messages for a business, representing the "flight plan".
    """
    logger.info(f"Fetching Autopilot flight plan for business_id: {business_id}")
    now_utc = datetime.now(timezone.utc)

    try:
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

        logger.info(f"Successfully found {len(scheduled_messages)} scheduled autopilot messages for business_id: {business_id}")
        return scheduled_messages

    except Exception as e:
        logger.error(
            f"A critical error occurred while fetching Autopilot plan for business_id {business_id}. Error: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while fetching the scheduled flight plan."
        )

@router.get("/full-customer-history", response_model=List[Dict[str, Any]])
def get_full_customer_history(business_id: int, db: Session = Depends(get_db)):
    """
    This endpoint is a placeholder for fetching a complete history across all customers.
    It is not yet implemented.
    """
    logger.warning(f"Endpoint /full-customer-history called for business_id {business_id}, but it is not implemented.")
    return []