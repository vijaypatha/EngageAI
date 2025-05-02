# app/routes/ai_routes.py

# You can add other AI-related routes here using the 'router' object
# For example:
# @router.post("/analyze-response", ...)
# async def analyze_response(...):
#    pass

# BUSINESS OWNER PERSPECTIVE:
# This file handles AI-powered functionalities that generate automated SMS roadmaps for engaging with customers.
# The core endpoint (/roadmap) creates a personalized sequence of SMS messages for a specific customer based on their
# profile, business context, and engagement stage. This automated engagement planning saves time while ensuring
# consistent, personalized customer communication.

# DEVELOPER PERSPECTIVE:
# Route: POST /ai/roadmap
# Service: Uses AIService.generate_roadmap() from app/services/ai_service.py

# Frontend Usage:
#   1. Onboarding flow: Called in frontend/src/app/onboarding/page.tsx when creating a new customer
#      (handleCustomerSubmit function around line 272-310)
#   2. Contact management: Called in frontend/src/app/contacts-ui/[id]/page.tsx for regenerating roadmaps
#      (regeneratePlan function around line 50-70)
#   3. Timeline preview: Used in frontend/src/components/TimelinePreview.tsx for refreshing engagement plans
#      (handleRegenerate function around line 42-63)
#
# Input: Requires customer_id and business_id in the RoadmapGenerate schema
# Output: Returns a RoadmapResponse schema with roadmap messages, status, and metadata
# Error Handling: Includes comprehensive error catching and logging for troubleshooting


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Customer, BusinessProfile # Removed unused imports like RoadmapMessageResponse here
from app.schemas import RoadmapGenerate, RoadmapResponse # Keep schema imports
from app.services.ai_service import AIService
# from app.auth import get_current_user # Uncomment if auth is added
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["ai"]
)

@router.post("/roadmap", response_model=RoadmapResponse)
async def generate_roadmap(
    data: RoadmapGenerate,
    db: Session = Depends(get_db),
    # current_user: dict = Depends(get_current_user) # Example if auth provides user info
):
    """
    Generates an AI-powered engagement roadmap (sequence of SMS messages)
    for a specific customer based on their profile and business context.
    """
    logger.info(f"Received roadmap generation request for customer_id: {data.customer_id}, business_id: {data.business_id}")
    try:
        # --- Basic Validation --- (Service layer also validates, but belt-and-suspenders)
        if not data.customer_id or not data.business_id:
             raise HTTPException(
                 status_code=status.HTTP_400_BAD_REQUEST,
                 detail="customer_id and business_id are required."
             )

        # --- Service Call ---
        ai_service = AIService(db)
        # The service handles DB lookups, AI call, DB creation, and returns the Pydantic model
        service_response: RoadmapResponse = await ai_service.generate_roadmap(data)

        # Log success confirmation
        logger.info(f"Successfully generated roadmap with {service_response.total_messages} messages for customer {data.customer_id}")
        # Log the actual roadmap list content for debugging if needed (can be verbose)
        # logger.debug(f"DEBUG: Roadmap content being returned in route: {service_response.roadmap}")

        # --- FIX: Return the Pydantic model instance directly ---
        # FastAPI uses the `response_model` to serialize this correctly.
        return service_response

    except HTTPException as http_exc:
        # Log and re-raise HTTP exceptions passed from the service or raised here
        logger.warning(f"HTTPException during roadmap generation for customer {data.customer_id}: {http_exc.status_code} - {http_exc.detail}")
        raise http_exc
    except Exception as e:
        # Log the full error with traceback for unexpected errors
        logger.exception(f"Unexpected error in generate_roadmap route for customer {data.customer_id}: {str(e)}")
        # Return a generic 500 error to the client
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred while generating the roadmap."
        )

