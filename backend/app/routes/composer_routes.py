# backend/app/routes/composer_routes.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import BusinessProfile
from app.services.instant_nudge_service import generate_instant_nudge

# Configure logger
logger = logging.getLogger(__name__)

# Define the router
router = APIRouter(prefix="/composer", tags=["composer"])

# --- Pydantic Models for this Route ---
class DraftRequest(BaseModel):
    topic: str = Field(..., description="The topic or subject for the AI message generation.")

class DraftResponse(BaseModel):
    message_draft: str

# --- API Endpoint ---
@router.post("/generate-draft", response_model=DraftResponse)
async def generate_composer_draft(
    payload: DraftRequest,
    db: Session = Depends(get_db),
    current_user: BusinessProfile = Depends(get_current_user)
):
    """
    Generates an AI-powered SMS message draft based on a topic and the
    authenticated business's style guide.
    """
    business_id = current_user.id
    logger.info(f"Received request to generate draft for business_id: {business_id} on topic: '{payload.topic}'")

    if not payload.topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Topic cannot be empty."
        )

    try:
        # Call the existing service function to generate the message content
        generated_data = await generate_instant_nudge(payload.topic, business_id, db)
        message_draft = generated_data.get("message")

        if not message_draft:
            logger.error(f"AI service returned an empty draft for business {business_id}, topic '{payload.topic}'.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI failed to generate a message draft."
            )
        
        logger.info(f"Successfully generated draft for business {business_id}.")
        return DraftResponse(message_draft=message_draft)

    except HTTPException as http_exc:
        # Re-raise known HTTP exceptions
        raise http_exc
    except Exception as e:
        logger.exception(f"An unexpected error occurred while generating draft for business {business_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during message generation."
        )