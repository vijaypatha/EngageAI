# backend/app/routes/style_routes.py

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models import BusinessProfile, BusinessOwnerStyle as BusinessOwnerStyleModel
from app.schemas import (
    SMSStyleInput,
    SMSStyleResponse,
    BusinessScenarioCreate,
    BusinessOwnerStyleRead, # This schema is expected to have a 'business_id' field
    StyleAnalysis
)
from pydantic import BaseModel
from app.services.style_service import StyleService
import json
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["style"]
)

class ScenariosListResponse(BaseModel):
    scenarios: List[BusinessOwnerStyleRead]

    class Config:
        from_attributes = True


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
        logger.error(f"Error training style: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to train style"
        )

@router.get("/{business_id}", response_model=SMSStyleResponse)
async def get_business_style(
    business_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieves the analyzed style guide for a business.
    """
    try:
        style_model = db.query(BusinessOwnerStyleModel).filter(
            BusinessOwnerStyleModel.business_id == business_id,
        ).order_by(BusinessOwnerStyleModel.last_analyzed.desc()).first()

        if not style_model:
            # Check if any style data exists, even if not fully "analyzed"
            any_style_data = db.query(BusinessOwnerStyleModel).filter(BusinessOwnerStyleModel.business_id == business_id).first()
            if not any_style_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No style guide or training data found for this business."
                )
            logger.info(f"Style data exists for business {business_id} but might not be fully analyzed/processed for SMSStyleResponse.")
            style_model = any_style_data # Use whatever data is found
        
        # Safely parse JSON fields, defaulting to empty structures if null or invalid
        def safe_json_load(data, default_type_constructor):
            if data is None:
                return default_type_constructor()
            if isinstance(data, (list, dict)): # Already parsed by SQLAlchemy JSON type
                return data
            try:
                return json.loads(data) if isinstance(data, str) else default_type_constructor()
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse JSON data: {data}, returning default.")
                return default_type_constructor()

        style_analysis_data = StyleAnalysis(
            key_phrases=safe_json_load(style_model.key_phrases, list),
            style_notes=safe_json_load(style_model.style_notes, dict),
            personality_traits=safe_json_load(style_model.personality_traits, list),
            message_patterns=safe_json_load(style_model.message_patterns, dict),
            special_elements=safe_json_load(style_model.special_elements, dict),
            overall_summary=getattr(style_model, 'overall_summary', '')
        )

        return SMSStyleResponse(
            status="success",
            message="Retrieved style guide analysis.",
            style_analysis=style_analysis_data
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting style guide for business {business_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not retrieve style guide: {str(e)}"
        )

@router.post("/scenarios/{business_id}", status_code=status.HTTP_201_CREATED, response_model=BusinessOwnerStyleRead)
async def create_business_scenario(
    business_id: int,
    scenario_data: BusinessScenarioCreate,
    db: Session = Depends(get_db)
):
    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business with id {business_id} not found"
        )
    
    db_scenario_data = scenario_data.model_dump()
    
    db_scenario = BusinessOwnerStyleModel(
        business_id=business_id,
        **db_scenario_data
    )
    if not hasattr(db_scenario, 'last_analyzed') or db_scenario.last_analyzed is None:
        db_scenario.last_analyzed = datetime.now(timezone.utc)

    try:
        db.add(db_scenario)
        db.commit()
        db.refresh(db_scenario)
        return db_scenario # Pydantic will convert this to BusinessOwnerStyleRead
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error creating scenario for business {business_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scenario might conflict with existing data.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create scenario for business {business_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scenario: {str(e)}"
        )

@router.get("/scenarios/{business_id}", response_model=ScenariosListResponse)
async def get_training_scenarios(
    business_id: int, # This is the business_id from the path
    db: Session = Depends(get_db),
    style_service: StyleService = Depends()
):
    """
    Retrieve training scenarios for a specific business.
    Ensures that each scenario item includes the 'business_id'.
    """
    # The service is expected to return a dictionary like {"scenarios": [list_of_scenario_data_items]}
    # where scenario_data_items are dictionaries or objects compatible with BusinessOwnerStyleRead,
    # but currently missing 'business_id'.
    service_response_dict = await style_service.get_training_scenarios(business_id, db)

    # Validate the structure of the service response
    if not isinstance(service_response_dict, dict) or 'scenarios' not in service_response_dict:
        logger.error(f"Service method get_training_scenarios for business_id {business_id} did not return a dict with 'scenarios' key. Response: {service_response_dict}")
        raise HTTPException(status_code=500, detail="Internal server error: Malformed response from style service.")

    scenarios_data_from_service = service_response_dict['scenarios']
    
    if not isinstance(scenarios_data_from_service, list):
        logger.error(f"The 'scenarios' field from service for business_id {business_id} is not a list. Found: {type(scenarios_data_from_service)}")
        raise HTTPException(status_code=500, detail="Internal server error: Scenarios data from service is not a list.")

    # --- MODIFICATION: Enrich each scenario item with business_id ---
    enriched_scenarios_list = []
    for scenario_item in scenarios_data_from_service:
        if isinstance(scenario_item, dict):
            # Add/overwrite business_id using the business_id from the path parameter
            # This ensures the BusinessOwnerStyleRead schema receives the required field.
            scenario_item['business_id'] = business_id 
            enriched_scenarios_list.append(scenario_item)
        elif hasattr(scenario_item, '__dict__') and hasattr(scenario_item, 'id'): # Check if it's an ORM model or similar object
            # If it's an ORM model, it should ideally already have business_id.
            # Pydantic's from_attributes should pick it up.
            # If BusinessOwnerStyleRead specifically needs it in dict form for some reason,
            # or if the object itself is missing business_id, this is more complex.
            # However, the error log's 'input' shows items are dicts.
            # For safety, if it's an object and doesn't have business_id, we could try setting it,
            # but direct dict manipulation is preferred if items are confirmed dicts.
            # This block is more of a fallback if service returns objects instead of dicts.
            logger.warning(f"Scenario item for business_id {business_id} is an object, not a dict. Ensuring business_id for Pydantic conversion if it's an ORM model passed directly: {type(scenario_item)}")
            # This assumes BusinessOwnerStyleRead can handle ORM models and find 'business_id'.
            # If the model object *itself* is missing business_id, it won't be added here magically for from_attributes.
            # The most reliable fix is if the service returns dicts, or ensures its ORM objects have business_id loaded.
            # Given the error log points to dicts, this path is less likely to be hit for this specific error.
            enriched_scenarios_list.append(scenario_item) 
        else:
            logger.error(f"Encountered unexpected item type in scenarios list for business_id {business_id}: {type(scenario_item)}. Item: {scenario_item}")
            # Skip invalid item or raise error, for now, we pass it and let validation fail more explicitly if needed
            enriched_scenarios_list.append(scenario_item) 
            
    # Construct the response using the (potentially) enriched list.
    # Pydantic will now validate each item in enriched_scenarios_list against BusinessOwnerStyleRead.
    return ScenariosListResponse(scenarios=enriched_scenarios_list)
    # --- END MODIFICATION ---


@router.put("/scenarios/{business_id}/{scenario_id}", response_model=BusinessOwnerStyleRead)
async def update_scenario_response(
    business_id: int,
    scenario_id: int,
    response: str = Body(..., embed=True), # Ensure response is correctly extracted
    db: Session = Depends(get_db),
    style_service: StyleService = Depends()
):
    """
    Update a business owner's response to a specific training scenario.
    """
    # The service method is expected to handle DB interactions and return an ORM model instance.
    updated_scenario_model = await style_service.update_scenario_response(scenario_id, business_id, response, db)
    if not updated_scenario_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found or update failed.")
    # Pydantic will convert updated_scenario_model to BusinessOwnerStyleRead
    return updated_scenario_model