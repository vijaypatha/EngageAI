# API endpoints for creating and managing automated message sequences
# Business owners can set up a series of messages to be sent to customers at specific times
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import RoadmapMessage
from app.schemas import RoadmapGenerate, RoadmapMessageResponse
from app.services.roadmap_service import RoadmapService
from typing import List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["roadmap"]
)

def get_roadmap_service(db: Session = Depends(get_db)) -> RoadmapService:
    return RoadmapService(db)

@router.post("/generate", response_model=List[RoadmapMessageResponse])
async def generate_roadmap(
    data: RoadmapGenerate,
    roadmap_service: RoadmapService = Depends(get_roadmap_service)
):
    """Generate a roadmap of SMS messages for a customer"""
    try:
        roadmap = await roadmap_service.generate_roadmap(data)
        return [RoadmapMessageResponse.model_validate(msg) for msg in roadmap]
    except Exception as e:
        logger.error(f"Error generating roadmap: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/{customer_id}/{business_id}", response_model=List[RoadmapMessageResponse])
async def get_roadmap(
    customer_id: int,
    business_id: int,
    roadmap_service: RoadmapService = Depends(get_roadmap_service)
):
    """Get roadmap messages for a customer"""
    try:
        roadmap = await roadmap_service.get_roadmap(customer_id, business_id)
        return [RoadmapMessageResponse.model_validate(msg) for msg in roadmap]
    except Exception as e:
        logger.error(f"Error getting roadmap: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.patch("/{roadmap_id}/status", response_model=RoadmapMessageResponse)
async def update_roadmap_status(
    roadmap_id: int,
    status: str,
    roadmap_service: RoadmapService = Depends(get_roadmap_service)
):
    """Update status of a roadmap message"""
    try:
        roadmap = await roadmap_service.update_roadmap_status(roadmap_id, status)
        return RoadmapMessageResponse.model_validate(roadmap)
    except Exception as e:
        logger.error(f"Error updating roadmap status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        ) 