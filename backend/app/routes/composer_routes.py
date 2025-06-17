# backend/app/routes/composer_routes.py
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.auth import get_current_user
from app.models import BusinessProfile, Customer, Tag
from app.services.instant_nudge_service import generate_instant_nudge
from app.services.ai_service import AIService
from app.schemas import (
    ComposerRoadmapRequest, 
    ComposerRoadmapResponse, 
    BatchRoadmapResponse, 
    RoadmapMessageOut,
    RoadmapGenerate
)

logger = logging.getLogger(__name__)

# --- THE FIX: The 'prefix' argument is removed from the APIRouter definition. ---
# The prefix is now correctly handled only once in main.py.
router = APIRouter(tags=["composer"])

# Pydantic models for this router's payloads
class DraftRequest(BaseModel):
    topic: str = Field(..., description="The topic or subject for the AI message generation.")
    business_id: int = Field(..., description="The ID of the business this draft is for.")

class DraftResponse(BaseModel):
    message_draft: str
    
def get_ai_service(db: Session = Depends(get_db)) -> AIService:
    return AIService(db=db)

@router.post("/generate-draft", response_model=DraftResponse)
async def generate_composer_draft(
    payload: DraftRequest,
    db: Session = Depends(get_db)
):
    """
    Generates an AI-powered SMS message draft based on a topic.
    """
    business_id = payload.business_id
    logger.info(f"Received request to generate draft for business_id: {business_id} on topic: '{payload.topic}'")
    if not payload.topic:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Topic cannot be empty.")
    try:
        generated_data = await generate_instant_nudge(payload.topic, business_id, db)
        message_draft = generated_data.get("message")
        if not message_draft:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI failed to generate a message draft.")
        return DraftResponse(message_draft=message_draft)
    except Exception as e:
        logger.exception(f"An unexpected error occurred while generating draft for business {business_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.post("/generate-roadmap-batch", response_model=BatchRoadmapResponse, summary="Generate AI Roadmaps for a Batch of Customers")
async def generate_roadmap_batch(
    payload: ComposerRoadmapRequest,
    db: Session = Depends(get_db),
    ai_service: AIService = Depends(get_ai_service)
):
    """
    Generates personalized AI roadmaps for a batch of customers,
    targeted either by a list of IDs or by tags.
    """
    log_prefix = f"[Composer B:{payload.business_id}]"
    logger.info(f"{log_prefix} Received batch roadmap generation request. Topic: '{payload.topic}'")

    if not payload.customer_ids and not payload.filter_tags:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either 'customer_ids' or 'filter_tags' must be provided.")
    if payload.customer_ids and payload.filter_tags:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide either 'customer_ids' or 'filter_tags', not both.")

    target_customer_ids = set()
    if payload.customer_ids:
        valid_customers_q = db.query(Customer.id).filter(Customer.business_id == payload.business_id, Customer.id.in_(payload.customer_ids))
        target_customer_ids = {res[0] for res in valid_customers_q.all()}
    elif payload.filter_tags:
        tag_names = [tag.strip().lower() for tag in payload.filter_tags if tag.strip()]
        if tag_names:
            query = db.query(Customer.id).join(Customer.tags).filter(Customer.business_id == payload.business_id, Tag.name.in_(tag_names)).group_by(Customer.id).having(func.count(Tag.id) == len(tag_names))
            target_customer_ids = {res[0] for res in query.all()}

    if not target_customer_ids:
        return BatchRoadmapResponse(status="success", message="No customers found matching the specified criteria.", generated_roadmaps=[])

    try:
        all_generated_roadmaps = []
        customers = db.query(Customer).filter(Customer.id.in_(list(target_customer_ids))).all()
        for customer in customers:
            roadmap_gen_payload = RoadmapGenerate(customer_id=customer.id, business_id=payload.business_id, context={"topic": payload.topic})
            single_roadmap_response = await ai_service.generate_roadmap(roadmap_gen_payload)
            
            if single_roadmap_response.status == "success" and single_roadmap_response.roadmap:
                roadmap_messages_out = [
                    RoadmapMessageOut(
                        id=msg.id,
                        customer_id=msg.customer_id,
                        customer_name=customer.customer_name,
                        smsContent=msg.message,
                        smsTiming=msg.smsTiming,
                        status=msg.status,
                        send_datetime_utc=msg.scheduled_time,
                        relevance=msg.relevance,
                        success_indicator=msg.success_indicator,
                        no_response_plan=msg.no_response_plan,
                        customer_timezone=customer.timezone
                    ) for msg in single_roadmap_response.roadmap
                ]
                all_generated_roadmaps.append(ComposerRoadmapResponse(
                    customer_id=customer.id,
                    customer_name=customer.customer_name,
                    roadmap_messages=roadmap_messages_out
                ))
        return BatchRoadmapResponse(status="success", message=f"Generated roadmaps for {len(all_generated_roadmaps)} customers.", generated_roadmaps=all_generated_roadmaps)
    except Exception as e:
        logger.error(f"{log_prefix} An unexpected error occurred during batch roadmap generation: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while generating roadmaps.")