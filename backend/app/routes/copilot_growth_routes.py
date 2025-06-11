# backend/app/routes/copilot_growth_routes.py
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessProfile
from app.auth import get_current_user
from app.services.copilot_growth_opportunity_service import CoPilotGrowthOpportunityService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/copilot-growth",
    tags=["AI Nudge Co-Pilot - Growth"]
)

# Dependency injector for the service
def get_growth_service(db: Session = Depends(get_db)) -> CoPilotGrowthOpportunityService:
    return CoPilotGrowthOpportunityService(db)

@router.post(
    "/nudges/{nudge_id}/launch-campaign",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Create a Draft Growth Campaign",
    description="Actions a GOAL_OPPORTUNITY nudge by creating editable draft messages for the targeted customers."
)
async def launch_growth_campaign(
    nudge_id: int,
    current_business_profile: BusinessProfile = Depends(get_current_user),
    growth_service: CoPilotGrowthOpportunityService = Depends(get_growth_service)
):
    """
    Endpoint to create draft campaign messages (e.g., referral, re-engagement) from a nudge.

    - Validates the user, nudge, and nudge type.
    - Calls the service to handle the batch message draft creation.
    - Updates the nudge status to ACTIONED.
    """
    try:
        log_prefix = f"[Route-CreateDraft B:{current_business_profile.id} N:{nudge_id}]"
        logger.info(f"{log_prefix} Received request to create draft growth campaign.")
        
        # The service method handles all logic, including validation, draft creation, and DB updates
        result = await growth_service.launch_growth_campaign_from_nudge(
            nudge_id=nudge_id,
            business_id_from_auth=current_business_profile.id
        )
        
        logger.info(f"{log_prefix} Successfully processed draft creation request. Result: {result}")
        return result
        
    except HTTPException as http_exc:
        logger.warning(f"{log_prefix} HTTPException during campaign draft creation: {http_exc.status_code} - {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"{log_prefix} Unexpected error during campaign draft creation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while creating the campaign drafts."
        )