# backend/app/routes/business_routes.py

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import pytz
from app.database import get_db
from app.models import BusinessProfile as BusinessProfileModel
from app.schemas import (
    BusinessProfileRead,
    BusinessProfileCreate,
    BusinessProfileUpdate,
    BusinessPhoneUpdate,
    AvailabilitySettingsData,
    SmartHoursConfigSchema, 
    ManualRuleSchema  
)
import re
import logging
from datetime import datetime, timedelta
from app import schemas
import json as py_json # For pretty printing in logs

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def slugify(name: str) -> str:
    name_str = str(name) if name is not None else ""
    name_str = name_str.strip().lower()
    name_str = re.sub(r'\s+', '-', name_str)
    name_str = re.sub(r'[^a-z0-9-]', '', name_str)
    return name_str.strip('-')

router = APIRouter(
    tags=["business"]
)

@router.post("/", response_model=BusinessProfileRead, status_code=status.HTTP_201_CREATED)
def create_business_profile(
    business: BusinessProfileCreate,
    db: Session = Depends(get_db)
):
    existing_business = db.query(BusinessProfileModel).filter(
        BusinessProfileModel.business_name == business.business_name
    ).first()
    if existing_business:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Business name already exists"
        )

    slug = slugify(business.business_name)
    existing_slug = db.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first()
    if existing_slug:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Generated slug '{slug}' from business name already exists."
        )
        
    db_business_data = business.model_dump()
    db_business = BusinessProfileModel(
        **db_business_data,
        slug=slug
    )
    try:
        db.add(db_business)
        db.commit()
        db.refresh(db_business)
        return db_business
    except IntegrityError as e:
        db.rollback()
        logger.error(f"DB integrity error creating business profile '{business.business_name}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A business with this name or slug already exists.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating business profile '{business.business_name}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create business profile.")

@router.get("/{business_id}", response_model=BusinessProfileRead)
def get_business_profile(business_id: int, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")
    return profile

@router.put("/{business_id}", response_model=BusinessProfileRead)
def update_business_profile(
    business_id: int,
    update_payload: BusinessProfileUpdate,
    db: Session = Depends(get_db)
):
    logger.info(f"Update request for business_id: {business_id}")
    logger.debug(f"Raw update_payload: {update_payload.model_dump(exclude_unset=True)}")
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found.")

    update_data_dict = update_payload.model_dump(exclude_unset=True)
    if not update_data_dict:
        return profile 

    if 'business_name' in update_data_dict and profile.business_name != update_data_dict['business_name']:
        new_slug = slugify(update_data_dict['business_name'])
        if new_slug != profile.slug:
            existing_slug_profile = db.query(BusinessProfileModel).filter(
                BusinessProfileModel.slug == new_slug, BusinessProfileModel.id != business_id
            ).first()
            if existing_slug_profile:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"New name generates conflicting slug '{new_slug}'.")
            profile.slug = new_slug

    for field, value in update_data_dict.items():
        setattr(profile, field, value)
    
    try:
        db.commit()
        db.refresh(profile)
        logger.info(f"Profile {business_id} updated. FAQ Auto-Reply: {profile.enable_ai_faq_auto_reply}")
        return profile
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating business profile {business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update profile.")

@router.get("/{business_id}/timezone", response_model=dict)
def get_business_timezone(business_id: int, db: Session = Depends(get_db)):
    # Corrected: Use .first() and extract the scalar value
    timezone_result = db.query(BusinessProfileModel.timezone).filter(BusinessProfileModel.id == business_id).first()
    if timezone_result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")
    timezone_val = timezone_result[0] # Extract the value from the tuple
    return {"timezone": timezone_val}

@router.put("/{business_id}/timezone", response_model=dict)
def update_business_timezone(business_id: int, timezone_payload: dict, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")
    new_timezone = timezone_payload.get("timezone")
    if not new_timezone or not isinstance(new_timezone, str):
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid 'timezone' string.")
    try:
        pytz.timezone(new_timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid timezone: {new_timezone}")
    profile.timezone = new_timezone
    try:
        db.commit()
        return {"timezone": profile.timezone}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update timezone.")

@router.get("/business-id/{business_name}", response_model=dict)
def get_business_id_by_name(business_name: str, db: Session = Depends(get_db)):
    # Corrected: Use .first() and extract the scalar value
    business_id_result = db.query(BusinessProfileModel.id).filter(BusinessProfileModel.business_name == business_name).first()
    if business_id_result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business '{business_name}' not found")
    business_id_val = business_id_result[0] # Extract the value from the tuple
    return {"business_id": business_id_val}

@router.get("/business-id/slug/{slug}", response_model=dict)
async def get_business_id_by_slug(slug: str, db: Session = Depends(get_db)):
    # Corrected: Use .first() and extract the scalar value
    business_id_result = db.query(BusinessProfileModel.id).filter(BusinessProfileModel.slug == slug).first()
    if business_id_result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with slug '{slug}' not found")
    business_id_val = business_id_result[0] # Extract the value from the tuple
    return {"business_id": business_id_val}

@router.get("/navigation-profile/slug/{slug}", response_model=BusinessProfileRead)
async def get_navigation_profile_by_slug(slug: str, db: Session = Depends(get_db)):
    business = db.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile for slug not found.")
    return business

@router.patch("/{business_id}/phone", response_model=BusinessProfileRead)
def update_business_phone(
    business_id: int,
    phone_update: BusinessPhoneUpdate,
    db: Session = Depends(get_db)
):
    business = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")
    business.business_phone_number = phone_update.business_phone_number
    try:
        db.commit()
        db.refresh(business)
        return business
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update phone.")

@router.delete("/abandoned", response_model=dict, status_code=status.HTTP_200_OK)
def cleanup_abandoned_profiles(db: Session = Depends(get_db)):
    cutoff_date = datetime.utcnow() - timedelta(days=7)
    query = db.query(BusinessProfileModel).filter(
        BusinessProfileModel.business_phone_number.is_(None),
        BusinessProfileModel.twilio_number.is_(None),
        BusinessProfileModel.created_at < cutoff_date
    )
    try:
        num_deleted = query.delete(synchronize_session=False)
        db.commit()
        return {"message": f"Deleted {num_deleted} abandoned profiles."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Cleanup failed.")

@router.get(
    "/{business_id}/availability-settings",
    response_model=schemas.AvailabilitySettingsData, # Use the new schema
    summary="Get Business Availability Settings"
)
def get_business_availability_settings(
    business_id: int,
    db: Session = Depends(get_db)
    # Add auth if needed: current_user: models.User = Depends(auth.get_current_active_user)
):
    logger.info(f"Fetching availability settings for business_id: {business_id}")
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        logger.warning(f"Business profile {business_id} not found when fetching availability settings.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")

    # Ensure default values are sensible if fields are null in DB
    # The model now has a default for availability_style = "smart_hours"
    # For smart_hours_config and manual_rules, they can be None/null if not set.
    # Frontend `page.tsx` already handles null/undefined for these and sets defaults.

    # Raw data from DB
    raw_smart_hours_config = profile.smart_hours_config
    raw_manual_rules = profile.manual_rules

    # Prepare response data
    response_data = {
        "availabilityStyle": profile.availability_style or "smart_hours", # Fallback if somehow null
        "smartHoursConfig": raw_smart_hours_config if raw_smart_hours_config is not None else None,
        "manualRules": raw_manual_rules if raw_manual_rules is not None else [] # Frontend expects an array
    }
    
    # Validate with Pydantic schema before returning (optional, but good practice)
    # This helps catch if DB data doesn't match schema expectations.
    try:
        validated_response = schemas.AvailabilitySettingsData(**response_data)
    except Exception as e: # Catch Pydantic validation error
        logger.error(f"Data validation error for availability settings for business {business_id}: {e}. Data: {response_data}", exc_info=True)
        # Fallback to defaults if validation fails, or raise 500
        # For now, let's try to return defaults that frontend can handle to avoid breaking UI completely.
        # The frontend page.tsx initializes these if not found.
        return schemas.AvailabilitySettingsData(
            availabilityStyle="smart_hours",
            smartHoursConfig=None, # Let frontend apply its defaults
            manualRules=[]
        )
        # Alternatively, raise HTTPException(status_code=500, detail="Error processing availability settings data.")

    logger.info(f"Successfully fetched availability settings for business {business_id}: Style='{validated_response.availabilityStyle}'")
    return validated_response

# --- NEW PUT ROUTE ---
@router.put(
    "/{business_id}/availability-settings",
    response_model=schemas.AvailabilitySettingsData,
    summary="Update Business Availability Settings"
)
def update_business_availability_settings(
    business_id: int,
    settings_data: schemas.AvailabilitySettingsData = Body(...),
    db: Session = Depends(get_db)
    # Add auth if needed
):
    logger.info(f"Attempting to update availability settings for business_id: {business_id}")
    # Log the structure of settings_data as parsed by Pydantic
    # model_dump_json is good for seeing the structure Pydantic understood
    logger.debug(f"Received parsed settings_data by Pydantic: {settings_data.model_dump_json(indent=2)}")

    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        logger.warning(f"Business profile {business_id} not found for update.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")

    # Update style
    profile.availability_style = settings_data.availabilityStyle
    logger.info(f"Business {business_id}: Set availability_style to '{profile.availability_style}'")

    # Reset configurations before applying the new one to ensure clean state
    current_smart_hours_config = None
    current_manual_rules = []

    if settings_data.availabilityStyle == "smart_hours":
        if settings_data.smartHoursConfig:
            # settings_data.smartHoursConfig is a SmartHoursConfigSchema instance
            current_smart_hours_config = settings_data.smartHoursConfig.model_dump()
            logger.debug(f"Business {business_id}: Preparing smart_hours_config: {py_json.dumps(current_smart_hours_config, indent=2)}")
        else:
            logger.debug(f"Business {business_id}: No smartHoursConfig provided for smart_hours style. Will be set to None.")
        # Manual rules should be empty for smart_hours style
        current_manual_rules = []
        logger.debug(f"Business {business_id}: Style is smart_hours, manual_rules will be cleared (set to []).")

    elif settings_data.availabilityStyle == "manual_slots":
        if settings_data.manualRules is not None: # Check if manualRules list is provided
            # settings_data.manualRules is a List[ManualRuleSchema]
            current_manual_rules = [rule.model_dump() for rule in settings_data.manualRules]
            logger.debug(f"Business {business_id}: Preparing manual_rules with {len(current_manual_rules)} items: {py_json.dumps(current_manual_rules, indent=2)}")
        else:
            # Should ideally be an empty list from Pydantic default_factory if not provided,
            # or if explicitly null in payload, then settings_data.manualRules is None.
            logger.debug(f"Business {business_id}: No manualRules list provided for manual_slots style. Will be set to [].")
            current_manual_rules = []
        # Smart hours config should be None for manual_slots style
        current_smart_hours_config = None
        logger.debug(f"Business {business_id}: Style is manual_slots, smart_hours_config will be cleared (set to None).")
        
    elif settings_data.availabilityStyle == "flexible_coordinator":
        logger.debug(f"Business {business_id}: Style is flexible_coordinator. Clearing smart_hours_config and manual_rules.")
        current_smart_hours_config = None
        current_manual_rules = []
    
    else: # Handle empty string "" or other unexpected styles that might pass Pydantic Literal validation if "" is part of it
        logger.warning(f"Business {business_id}: Unknown or empty availability style '{settings_data.availabilityStyle}'. Clearing both configs.")
        current_smart_hours_config = None
        current_manual_rules = []

    # Assign the processed configurations
    profile.smart_hours_config = current_smart_hours_config
    profile.manual_rules = current_manual_rules # Assigning Python list

    profile.updated_at = datetime.utcnow() # Or use timezone.utc if you have that imported

    try:
        db.commit()
        db.refresh(profile)
        logger.info(f"Successfully SAVED availability settings for business {business_id}. Style: '{profile.availability_style}'")
        logger.debug(f"DB smart_hours_config after save: {profile.smart_hours_config}") # Log what's in the model post-commit/refresh
        logger.debug(f"DB manual_rules after save: {profile.manual_rules}") # Log what's in the model post-commit/refresh

        # Construct response ensuring correct types for potentially None values
        # The Pydantic response model will handle the final serialization to JSON for the client
        return schemas.AvailabilitySettingsData(
            availabilityStyle=profile.availability_style,
            smartHoursConfig=profile.smart_hours_config, # Pass the dict/None
            manualRules=profile.manual_rules if profile.manual_rules is not None else [] # Pass the list/[]
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error during DB commit for availability settings, business {business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not save availability settings.")