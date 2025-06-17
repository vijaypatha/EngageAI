# backend/app/routes/ai_routes.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import RoadmapGenerate, RoadmapResponse
from app.services.ai_service import AIService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["ai"]
)

@router.post("/roadmap", response_model=RoadmapResponse)
async def generate_roadmap(
    data: RoadmapGenerate,
    db: Session = Depends(get_db)
):
    """
    Generates an AI-powered engagement roadmap for a single customer.
    """
    logger.info(f"Received single roadmap generation request for customer_id: {data.customer_id}")
    try:
        ai_service = AIService(db)
        service_response = await ai_service.generate_roadmap(data)
        logger.info(f"Successfully generated roadmap with {service_response.total_messages} messages for customer {data.customer_id}")
        return service_response
    except HTTPException as http_exc:
        logger.warning(f"HTTPException during roadmap generation for customer {data.customer_id}: {http_exc.status_code} - {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.exception(f"Unexpected error in generate_roadmap route for customer {data.customer_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred while generating the roadmap."
        )