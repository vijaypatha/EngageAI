# backend/app/routes/copilot_nudge_routes.py
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone # Import datetime & timezone

from app.database import get_db
from app.models import CoPilotNudge, Customer, NudgeStatusEnum, BusinessProfile
from app.schemas import (
    CoPilotNudgeRead,
    DismissNudgePayload,
    SentimentActionPayload,
)
from app.auth import get_current_user # For authentication and getting business_id
from app.services.copilot_nudge_action_service import CoPilotNudgeActionService
# NudgeGenerationService might not be directly used in these specific routes for Iteration 1,
# but good to have if other nudge management routes are added later.
# from app.services.copilot_nudge_generation_service import CoPilotNudgeGenerationService


logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["AI Nudge Co-Pilot"]
)

# Dependency for CoPilotNudgeActionService
def get_copilot_nudge_action_service(db: Session = Depends(get_db)) -> CoPilotNudgeActionService:
    return CoPilotNudgeActionService(db)

@router.get("/nudges", response_model=List[CoPilotNudgeRead])
async def get_active_nudges(
    db: Session = Depends(get_db),
    current_business_profile: BusinessProfile = Depends(get_current_user)
):
    """
    Fetches active CoPilotNudge records for the authenticated business.
    Includes customer_name if the nudge is associated with a customer.
    """
    # --- START MODIFICATION ---
    logger.info("✅ --- Received request for /nudges endpoint. --- ✅")
    # --- END MODIFICATION ---
    business_id = current_business_profile.id
    logger.info(f"Fetching active CoPilotNudges for business_id: {business_id}")

    nudges_orm = (
        db.query(CoPilotNudge)
        .outerjoin(Customer, CoPilotNudge.customer_id == Customer.id) # outerjoin in case customer_id is None
        .filter(
            CoPilotNudge.business_id == business_id,
            CoPilotNudge.status == NudgeStatusEnum.ACTIVE.value # Filter by active status
        )
        .order_by(CoPilotNudge.created_at.desc())
        .add_columns(Customer.customer_name) # Select customer_name explicitly
        .all()
    )

    response_nudges = []
    for nudge, customer_name in nudges_orm:
        nudge_read = CoPilotNudgeRead.model_validate(nudge)
        nudge_read.customer_name = customer_name # Assign fetched customer_name
        response_nudges.append(nudge_read)
    
    logger.info(f"Returning {len(response_nudges)} active CoPilotNudges for business_id: {business_id}")
    return response_nudges

@router.post("/nudges/{nudge_id}/dismiss", response_model=CoPilotNudgeRead)
async def dismiss_nudge(
    nudge_id: int,
    payload: DismissNudgePayload,
    db: Session = Depends(get_db),
    current_business_profile: BusinessProfile = Depends(get_current_user)
):
    """
    Dismisses a CoPilotNudge, updating its status.
    Optionally logs a reason for dismissal.
    """
    business_id = current_business_profile.id
    logger.info(f"Dismissing CoPilotNudge ID: {nudge_id} for business_id: {business_id}. Reason: {payload.reason}")

    nudge = db.query(CoPilotNudge).filter(
        CoPilotNudge.id == nudge_id,
        CoPilotNudge.business_id == business_id
    ).first()

    if not nudge:
        logger.warning(f"CoPilotNudge ID {nudge_id} not found for business {business_id} to dismiss.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nudge not found.")

    if nudge.status == NudgeStatusEnum.DISMISSED.value:
        logger.info(f"Nudge {nudge_id} is already dismissed.")
        # Return current state or an appropriate message
        nudge_read = CoPilotNudgeRead.model_validate(nudge)
        if nudge.customer_id: # Populate customer_name if it exists
            customer = db.query(Customer.customer_name).filter(Customer.id == nudge.customer_id).scalar_one_or_none()
            nudge_read.customer_name = customer
        return nudge_read

    nudge.status = NudgeStatusEnum.DISMISSED.value
    # Optionally, store payload.reason in nudge.ai_suggestion_payload or a new field if needed
    if payload.reason:
        if nudge.ai_suggestion_payload is None:
            nudge.ai_suggestion_payload = {}
        nudge.ai_suggestion_payload['dismissal_reason'] = payload.reason
        
    nudge.updated_at = datetime.now(timezone.utc)
    
    db.add(nudge)
    db.commit()
    db.refresh(nudge)
    
    logger.info(f"CoPilotNudge ID {nudge_id} successfully dismissed for business_id: {business_id}.")
    
    nudge_read = CoPilotNudgeRead.model_validate(nudge)
    if nudge.customer_id: # Populate customer_name
        customer = db.query(Customer.customer_name).filter(Customer.id == nudge.customer_id).scalar_one_or_none()
        nudge_read.customer_name = customer
    return nudge_read


@router.post("/nudges/{nudge_id}/sentiment-action", response_model=CoPilotNudgeRead)
async def handle_sentiment_action(
    nudge_id: int,
    payload: SentimentActionPayload,
    db: Session = Depends(get_db),
    current_business_profile: BusinessProfile = Depends(get_current_user),
    action_service: CoPilotNudgeActionService = Depends(get_copilot_nudge_action_service)
):
    """
    Handles actions for sentiment-based CoPilotNudges, like requesting a review.
    """
    business_id = current_business_profile.id
    logger.info(f"Handling sentiment action '{payload.action_type}' for CoPilotNudge ID: {nudge_id}, Business ID: {business_id}")

    if payload.action_type.upper() == "REQUEST_REVIEW":
        try:
            updated_nudge = await action_service.handle_request_review_action(
                nudge_id=nudge_id,
                business_id=business_id
            )
            nudge_read = CoPilotNudgeRead.model_validate(updated_nudge)
            if updated_nudge.customer_id: # Populate customer_name
                customer_name = db.query(Customer.customer_name).filter(Customer.id == updated_nudge.customer_id).scalar_one_or_none()
                nudge_read.customer_name = customer_name
            return nudge_read
        except HTTPException as http_exc:
            # Log the specific HTTP exception details before re-raising
            logger.error(f"HTTPException during 'REQUEST_REVIEW' action for nudge {nudge_id}: {http_exc.status_code} - {http_exc.detail}")
            raise http_exc
        except ValueError as ve: # Catch ValueErrors from service layer, e.g., customer not found
            logger.error(f"ValueError during 'REQUEST_REVIEW' action for nudge {nudge_id}: {str(ve)}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
        except Exception as e:
            logger.error(f"Unexpected error during 'REQUEST_REVIEW' action for nudge {nudge_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while processing the action.")
    else:
        logger.warning(f"Unsupported action_type '{payload.action_type}' for sentiment action on nudge {nudge_id}.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported action_type: {payload.action_type}")