# backend/app/routes/targeted_event_routes.py
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessProfile
from app.schemas import ConfirmTimedCommitmentPayload
from app.services.targeted_event_service import TargetedEventService # Import the new service
from app.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/targeted-events",
    tags=["Targeted Events"]
)

# Dependency injector for the service
def get_targeted_event_service(db: Session = Depends(get_db)) -> TargetedEventService:
    return TargetedEventService(db)

@router.post(
    "/confirm-from-nudge/{nudge_id}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Confirm a Potential Timed Commitment from a Nudge",
    description=(
        "Confirms a potential event, creates a TargetedEvent record, "
        "sends a confirmation SMS to the customer, notifies the business owner, "
        "and automatically schedules standard event reminders (24hr and 1hr prior)."
    )
)
async def confirm_potential_event_from_nudge(
    nudge_id: int,
    payload: ConfirmTimedCommitmentPayload,
    current_business_profile: BusinessProfile = Depends(get_current_user),
    event_service: TargetedEventService = Depends(get_targeted_event_service)
):
    """
    Endpoint to confirm an AI-detected potential event.

    - **Validates** the nudge and user authorization.
    - **Creates** a `TargetedEvent` in the database.
    - **Sends** a clean confirmation SMS to the customer.
    - **Notifies** the business owner via SMS.
    - **Schedules** standard reminders automatically.
    - **Updates** the original nudge's status to `ACTIONED`.
    """
    try:
        logger.info(
            f"Received request to confirm event from nudge ID: {nudge_id} "
            f"for business ID: {current_business_profile.id}"
        )
        
        confirmation_result = await event_service.confirm_event_from_nudge(
            nudge_id=nudge_id,
            payload=payload,
            business_id_from_auth=current_business_profile.id,
            owner_phone_number=current_business_profile.business_phone_number # Pass owner's phone for notification
        )
        
        logger.info(f"Successfully confirmed event from nudge ID: {nudge_id}. Result: {confirmation_result}")
        return confirmation_result
        
    except HTTPException as http_exc:
        logger.warning(f"HTTPException confirming event from nudge ID {nudge_id}: {http_exc.status_code} - {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error confirming event from nudge ID {nudge_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred while confirming the event: {str(e)}"
        )
