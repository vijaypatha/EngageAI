# backend/app/routes/instant_nudge_routes.py

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, status, Query 
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession 
from sqlalchemy import func, select 

from app.database import get_async_db 
from app.models import (
    BusinessProfile,
    Message,
    Customer as CustomerModel,
    Tag,
    MessageTypeEnum
)
from app.services.instant_nudge_service import generate_instant_nudge, handle_instant_nudge_batch
from app.schemas import InstantNudgeSendPayload

from app import auth, models, schemas 
from app.config import Settings, get_settings 

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Instant Nudge"]
)

class InstantNudgeTargetingRequest(BaseModel):
    topic: str = Field(..., description="The topic/subject for the AI message generation.")
    business_id: int = Field(..., description="The ID of the business sending the nudge.")
    customer_ids: Optional[List[int]] = Field(None, description="Optional: Specific list of customer IDs to target.")
    filter_tags: Optional[List[str]] = Field(None, description="Optional: List of tag names (lowercase) to filter customers by (matches ALL tags).")


@router.post("/generate-targeted-draft", response_model=Dict[str, Any])
async def generate_targeted_nudge_draft(
    payload: InstantNudgeTargetingRequest,
    db: AsyncSession = Depends(get_async_db), 
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business)
):
    # Capture business ID early for safe logging
    auth_business_id = current_business.id
    
    logger.info(
        f"Nudge Draft: Request by Business ID {auth_business_id} for payload business_id={payload.business_id} "
        f"| topic='{payload.topic}' | tags='{payload.filter_tags}' | specific_ids='{payload.customer_ids}'"
    )

    if payload.business_id != auth_business_id:
        logger.warning(
            f"Nudge Draft AuthZ Error: Auth Business ID {auth_business_id} "
            f"does not match payload business_id {payload.business_id}."
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this business.")

    target_customer_ids = set()

    if payload.customer_ids and payload.filter_tags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either 'customer_ids' or 'filter_tags', not both."
        )

    if payload.customer_ids:
        target_customer_ids = set(payload.customer_ids)
        stmt_valid_customers = select(CustomerModel.id).where(
            CustomerModel.business_id == auth_business_id, 
            CustomerModel.id.in_(target_customer_ids)
        )
        result_valid_customers = await db.execute(stmt_valid_customers)
        valid_customer_ids = {res[0] for res in result_valid_customers.all()}
        
        if len(valid_customer_ids) != len(target_customer_ids):
            invalid_ids = target_customer_ids - valid_customer_ids
            logger.warning(f"Nudge Draft: Provided customer IDs not found or not linked to business {auth_business_id}: {invalid_ids}")
            target_customer_ids = valid_customer_ids 
        logging.info(f"Nudge Draft: Targeting specific customer IDs (validated for business {auth_business_id}): {target_customer_ids}")

    elif payload.filter_tags:
        tag_names = [tag.strip().lower() for tag in payload.filter_tags if tag.strip()]
        if tag_names:
            logging.info(f"Nudge Draft: Filtering customers for business {auth_business_id} by tags: {tag_names}")
            subquery = (
                select(CustomerModel.id)
                .join(CustomerModel.tags)
                .where(CustomerModel.business_id == auth_business_id)
                .where(Tag.name.in_(tag_names))
                .group_by(CustomerModel.id)
                .having(func.count(Tag.id) == len(tag_names))
            )
            result_tags = await db.execute(subquery)
            customer_ids_from_tags = {res[0] for res in result_tags.all()}
            target_customer_ids = customer_ids_from_tags
            logging.info(f"Nudge Draft: Found {len(target_customer_ids)} customers matching tags for business {auth_business_id}: {target_customer_ids}")
        else:
            logging.warning("Nudge Draft: filter_tags provided but resulted in empty list after cleaning.")
            target_customer_ids = set()
    else:
        logging.error("Nudge Draft: Targeting request must include either 'customer_ids' or 'filter_tags'.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request must include customer_ids or filter_tags to identify targets."
        )

    if not target_customer_ids:
        logging.warning(f"Nudge Draft: No target customers identified for business {auth_business_id}.")
        return {
            "message_draft": None,
            "target_customer_count": 0,
            "target_customer_ids": [],
            "status": "No customers found matching criteria."
        }

    try:
        generated_data = await generate_instant_nudge(
            db=db, 
            topic=payload.topic, 
            business_id=auth_business_id 
        )
        message_draft = generated_data.get("message")
        logger.info(f"Nudge Draft: Generated for topic '{payload.topic}' for business {auth_business_id}.")
        if not message_draft:
             logger.error(f"Nudge Draft: AI service returned empty message draft for business {auth_business_id}.")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate message draft content.")
        return {
            "message_draft": message_draft,
            "target_customer_count": len(target_customer_ids),
            "target_customer_ids": sorted(list(target_customer_ids))
        }
    except Exception as e:
        logger.error(f"Nudge Draft: Generation failed for business {auth_business_id}: {e}", exc_info=True)
        if isinstance(e, HTTPException):
             raise e
        raise HTTPException(status_code=500, detail=f"Failed to generate instant nudge message: {str(e)}")


@router.post("/send-batch", status_code=status.HTTP_202_ACCEPTED, response_model=Dict[str, Any])
async def send_instant_nudge_batch_final(
    payload: InstantNudgeSendPayload,
    db: AsyncSession = Depends(get_async_db), 
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business)
):
    # Capture business ID early for safe logging
    auth_business_id = current_business.id

    logger.info(
        f"Nudge Send Batch: Request by Business ID {auth_business_id} for payload business_id={payload.business_id}. "
        f"Customers: {len(payload.customer_ids)}. Is Appointment: {payload.is_appointment_proposal}"
    )

    if payload.business_id != auth_business_id:
        logger.warning(
            f"Nudge Send Batch AuthZ Error: Auth Business ID {auth_business_id} "
            f"does not match payload business_id {payload.business_id}."
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this business.")

    if not payload.customer_ids:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="customer_ids list cannot be empty.")
    if not payload.message:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message content cannot be empty.")

    try:
        result = await handle_instant_nudge_batch(
             db=db, 
             payload=payload,
             business=current_business, 
        )
        logger.info(f"Nudge Send Batch: Processing initiated for business {auth_business_id}. Result: {result.get('message')}")
        return result

    except ValueError as ve:
         logger.error(f"Nudge Send Batch: Value error for business {auth_business_id}: {ve}", exc_info=True) # Use captured ID
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except HTTPException as he:
        # If it's an HTTPException, it might already have important details
        logger.error(f"Nudge Send Batch: HTTP Exception for business {auth_business_id}: {he.detail}", exc_info=True) # Use captured ID
        raise he
    except Exception as e:
        # For other exceptions, log with the captured ID
        logger.error(f"Nudge Send Batch: Failed for business {auth_business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process nudge batch: {str(e)}")


# --- Analytics/Status Endpoints (Ensure async correctness) ---

@router.get("/instant-status/slug/{slug}")
async def get_instant_nudge_status_by_slug( 
    slug: str, 
    db: AsyncSession = Depends(get_async_db)
):
    stmt_business = select(BusinessProfile).where(BusinessProfile.slug == slug)
    result_business = await db.execute(stmt_business)
    business = result_business.scalar_one_or_none()
    
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    
    stmt_messages = select(Message).where(
        Message.business_id == business.id,
        Message.message_metadata.op('->>')('source') == 'instant_nudge' 
    ).order_by(Message.created_at.desc())
    
    result_messages = await db.execute(stmt_messages)
    messages = result_messages.scalars().all()

    return [
        {
            "id": m.id, "message": m.content, "customer_id": m.customer_id,
            "status": m.status.value if m.status else None, 
            "send_time": m.scheduled_send_at or m.sent_at or m.created_at,
            "is_hidden": m.is_hidden,
            "conversation_id": str(m.conversation_id) if m.conversation_id else None,
            "message_type": m.message_type.value if m.message_type else None,
            "metadata": m.message_metadata
        } for m in messages
    ]


@router.get("/nudge/instant-analytics/business/{business_id_in_path}") 
async def get_instant_nudge_analytics(
    business_id_in_path: int, 
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business)
):
    auth_business_id = current_business.id # Capture ID early
    if business_id_in_path != auth_business_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this business's analytics.")

    now_utc = datetime.now(timezone.utc)
    
    stmt_messages = select(Message).where(
        Message.business_id == auth_business_id,
        Message.message_metadata.op('->>')('source') == 'instant_nudge'
    )
    result_messages = await db.execute(stmt_messages)
    messages = result_messages.scalars().all()
    
    total_sent = sum(1 for m in messages if m.status == models.MessageStatusEnum.SENT)
    total_scheduled = sum(1 for m in messages if m.status == models.MessageStatusEnum.SCHEDULED and m.scheduled_send_at and m.scheduled_send_at > now_utc)
    total_failed = sum(1 for m in messages if m.status == models.MessageStatusEnum.FAILED)
    appointment_proposals_initiated = sum(
        1 for m in messages if m.message_type == models.MessageTypeEnum.APPOINTMENT_PROPOSAL
    )

    return {
        "total_messages_via_instant_nudge": len(messages),
        "sent": total_sent,
        "scheduled_future": total_scheduled,
        "failed": total_failed,
        "appointment_proposals_initiated": appointment_proposals_initiated,
        "success_rate_attempted_sends": (total_sent / (total_sent + total_failed)) if (total_sent + total_failed) > 0 else 0
    }


@router.get("/nudge/instant-multi/customer/{customer_id}")
async def get_instant_nudges_for_customer(
    customer_id: int, 
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business)
):
     auth_business_id = current_business.id # Capture ID early
     customer_stmt = select(CustomerModel).where(
         CustomerModel.id == customer_id,
         CustomerModel.business_id == auth_business_id 
     )
     result_customer = await db.execute(customer_stmt)
     customer = result_customer.scalar_one_or_none()

     if not customer:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found for this business.")

     messages_stmt = select(Message).where(
        Message.customer_id == customer_id,
        Message.business_id == auth_business_id, 
        Message.message_metadata.op('->>')('source') == 'instant_nudge'
     ).order_by(Message.created_at.desc())
     
     result_messages = await db.execute(messages_stmt)
     messages = result_messages.scalars().all()
     
     return [
        {
            "id": m.id, "message": m.content, "customer_id": m.customer_id,
            "status": m.status.value if m.status else None, 
            "send_time": m.scheduled_send_at or m.sent_at or m.created_at,
            "is_hidden": m.is_hidden,
            "message_type": m.message_type.value if m.message_type else None,
            "conversation_id": str(m.conversation_id) if m.conversation_id else None,
            "metadata": m.message_metadata
        } for m in messages
    ]