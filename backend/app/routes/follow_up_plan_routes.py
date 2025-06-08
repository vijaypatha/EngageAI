# backend/app/routes/follow_up_plan_routes.py
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessProfile
from app.schemas import ActivateEngagementPlanPayload # This payload is used to activate the plan
from app.services.follow_up_plan_service import FollowUpPlanService # Import the newly named service
from app.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Follow-up Nudge Plans"]  # Tag for API documentation
)

# Dependency injector for FollowUpPlanService
def get_follow_up_plan_service(db: Session = Depends(get_db)) -> FollowUpPlanService:
    return FollowUpPlanService(db)

@router.post(
    "/activate-from-nudge/{nudge_id}",
    response_model=Dict[str, Any], # The service returns a dictionary
    status_code=status.HTTP_202_ACCEPTED, # 202 for actions that are processed asynchronously
    summary="Activate an AI-Drafted Follow-up Nudge Plan",
    description="Activates a STRATEGIC_ENGAGEMENT_OPPORTUNITY nudge, creating and scheduling the sequence of messages in the plan."
)
async def activate_follow_up_plan_from_nudge(
    nudge_id: int,
    payload: ActivateEngagementPlanPayload,
    current_business_profile: BusinessProfile = Depends(get_current_user),
    plan_service: FollowUpPlanService = Depends(get_follow_up_plan_service)
):
    """
    Endpoint to activate an AI-drafted Follow-up Nudge Plan.
    
    When a business owner confirms the plan:
    - Validates the nudge and user authorization.
    - Calls the service to create and schedule all messages in the plan.
    - Updates the original nudge status to ACTIONED.
    """
    try:
        logger.info(f"Received request to activate follow-up plan from nudge ID: {nudge_id} for business ID: {current_business_profile.id}")
        
        activation_result = await plan_service.activate_plan_from_nudge(
            nudge_id=nudge_id,
            payload=payload,
            business_id_from_auth=current_business_profile.id
        )
        
        logger.info(f"Successfully initiated activation of plan from nudge ID: {nudge_id}. Result: {activation_result}")
        return activation_result
        
    except HTTPException as http_exc:
        # Re-raise HTTPExceptions from the service (e.g., 404 Nudge not found)
        logger.warning(f"HTTPException activating plan from nudge ID {nudge_id}: {http_exc.status_code} - {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error activating plan from nudge ID {nudge_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred while activating the plan: {str(e)}"
        )

# Future routes related to managing active plans could go here, for example:
# GET /follow-up-plans/customer/{customer_id} (to see active plans)
# POST /follow-up-plans/{plan_instance_id}/pause (to pause an active plan)
