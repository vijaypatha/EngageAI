# API endpoints for training and managing business communication style
# Business owners can teach the system their preferred way of communicating with customers
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BusinessProfile, BusinessOwnerStyle
from app.schemas import (
    SMSStyleInput, 
    SMSStyleResponse, 
    BusinessScenarioCreate,
    BusinessOwnerStyleResponse
)
from app.services.style_service import StyleService
from app.auth import get_current_user
import json
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone # Added timezone

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["style"]
)

@router.post("/train", response_model=SMSStyleResponse)
async def train_business_style(
    style_data: List[SMSStyleInput],
    db: Session = Depends(get_db),
    style_service: StyleService = Depends()
):
    """Train business style using provided responses to scenarios."""
    try:
        if not style_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No training data provided"
            )
        
        result = await style_service.train_style(style_data, db)
        return result
        
    except ValueError as e:
        logger.error(f"Validation error in training style: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error training style: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to train style"
        )

@router.get("/{business_id}", response_model=SMSStyleResponse)
async def get_business_style(
    business_id: int,
    db: Session = Depends(get_db)
):
    try:
        # Get the most recent style analysis
        style = db.query(BusinessOwnerStyle).filter(
            BusinessOwnerStyle.business_id == business_id,
            BusinessOwnerStyle.key_phrases.isnot(None)  # ensure we get one with analysis
        ).order_by(BusinessOwnerStyle.last_analyzed.desc()).first()

        if not style:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No style guide found for this business"
            )

        # Convert DB data to StyleAnalysis format
        style_analysis = {
            "key_phrases": json.loads(style.key_phrases) if style.key_phrases else [],
            "style_notes": json.loads(style.style_notes) if style.style_notes else {},
            "personality_traits": json.loads(style.personality_traits) if style.personality_traits else [],
            "message_patterns": json.loads(style.message_patterns) if style.message_patterns else {},
            "special_elements": json.loads(style.special_elements) if style.special_elements else {},
            "overall_summary": getattr(style, 'overall_summary', '')  # if you added this field
        }

        # Return with populated style_analysis
        return SMSStyleResponse(
            status="success",
            style_analysis=style_analysis
        )

    except Exception as e:
        logger.error(f"Error getting style guide: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/scenarios/{business_id}", status_code=status.HTTP_201_CREATED, response_model=BusinessOwnerStyleResponse)
async def create_business_scenario(
    business_id: int,
    scenario: BusinessScenarioCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new business scenario.
    """
    # Check if business exists
    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business with id {business_id} not found"
        )

    # Create new scenario
    db_scenario = BusinessOwnerStyle(
        business_id=business_id,
        scenario=scenario.scenario,
        context_type=scenario.context_type,
        key_phrases=scenario.key_phrases,
        style_notes=scenario.style_notes,
        personality_traits=scenario.personality_traits,
        message_patterns=scenario.message_patterns,
        special_elements=scenario.special_elements,
        response=scenario.response or "",
        last_analyzed=datetime.now(timezone.utc)
    )

    try:
        db.add(db_scenario)
        db.commit()
        db.refresh(db_scenario)
        return db_scenario
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create scenario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scenario: {str(e)}"
        )

@router.get("/scenarios/{business_id}")
async def get_training_scenarios(
    business_id: int, 
    db: Session = Depends(get_db),
    style_service: StyleService = Depends()
):
    """
    Retrieve training scenarios for a specific business.
    If no scenarios exist, returns default scenarios.
    """
    return await style_service.get_training_scenarios(business_id, db)

@router.put("/scenarios/{business_id}/{scenario_id}", response_model=BusinessOwnerStyleResponse)
async def update_scenario_response(
    business_id: int,
    scenario_id: int,
    response: str = Body(...),
    db: Session = Depends(get_db),
    style_service: StyleService = Depends()
):
    """
    Update a business owner's response to a training scenario.
    """
    return await style_service.update_scenario_response(scenario_id, business_id, response, db) 