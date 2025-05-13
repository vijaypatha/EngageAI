# backend/app/routes/business_routes.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError # Good to have for create endpoint

from app.database import get_db
from app.models import BusinessProfile as BusinessProfileModel
from app.schemas import (
    BusinessProfile,
    BusinessProfileCreate,
    BusinessProfileUpdate, # This schema must include the new Autopilot fields
    BusinessPhoneUpdate
)
import re
import logging
from datetime import datetime, timedelta # Added timedelta back

# Configure logger
logger = logging.getLogger(__name__)

def slugify(name: str) -> str:
    name_str = str(name) if name is not None else ""
    name_str = name_str.strip().lower()
    name_str = re.sub(r'\s+', '-', name_str)
    name_str = re.sub(r'[^a-z0-9-]', '', name_str) # Keep only lowercase alphanumeric and hyphens
    return name_str.strip('-') # Remove leading/trailing hyphens

router = APIRouter(
    tags=["business"]
)

@router.post("/", response_model=BusinessProfile, status_code=status.HTTP_201_CREATED)
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
            detail=f"Generated slug '{slug}' from business name already exists. Please try a slightly different business name."
        )
        
    db_business = BusinessProfileModel(
        **business.model_dump(),
        slug=slug
    )
    try:
        db.add(db_business)
        db.commit()
        db.refresh(db_business)
        return BusinessProfile.from_orm(db_business)
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error creating business profile '{business.business_name}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A business with this name or resulting slug already exists.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating business profile '{business.business_name}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create business profile.")

@router.get("/{business_id}", response_model=BusinessProfile)
def get_business_profile(business_id: int, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")
    return BusinessProfile.from_orm(profile)

@router.put("/{business_id}", response_model=BusinessProfile)
def update_business_profile(
    business_id: int,
    update_payload: BusinessProfileUpdate,
    db: Session = Depends(get_db)
):
    logger.info(f"Received update request for business_id: {business_id}")
    logger.debug(f"Raw update_payload received: {update_payload.model_dump()}")

    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        logger.warning(f"Business profile {business_id} not found for update.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")

    update_data_dict = update_payload.model_dump(exclude_unset=True)
    logger.info(f"Data to update (exclude_unset=True): {update_data_dict}")

    if not update_data_dict:
        logger.warning(f"No update data provided for business {business_id} after exclude_unset.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided.")

    if 'enable_ai_faq_auto_reply' in update_data_dict:
        logger.info(f"Found 'enable_ai_faq_auto_reply' in update data with value: {update_data_dict['enable_ai_faq_auto_reply']} (Type: {type(update_data_dict['enable_ai_faq_auto_reply'])})")
    else:
        logger.info("'enable_ai_faq_auto_reply' key NOT found in update_data_dict (after exclude_unset).")

    if 'business_name' in update_data_dict and profile.business_name != update_data_dict['business_name']:
        new_slug = slugify(update_data_dict['business_name'])
        if new_slug != profile.slug:
            existing_slug_profile = db.query(BusinessProfileModel).filter(
                BusinessProfileModel.slug == new_slug, BusinessProfileModel.id != business_id
            ).first()
            if existing_slug_profile:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"New business name generates a slug ('{new_slug}') that already exists.")
            logger.info(f"Updating slug from '{profile.slug}' to '{new_slug}' due to business name change.")
            profile.slug = new_slug

    logger.info(f"Applying updates to profile {business_id}...")
    for field, value in update_data_dict.items():
        logger.debug(f"Setting attribute '{field}' to value '{value}' (Type: {type(value)})")
        setattr(profile, field, value)
    
    try:
        logger.info(f"Attempting to commit changes for business {business_id}...")
        db.commit()
        db.refresh(profile)
        logger.info(f"Successfully updated and committed profile {business_id}.")
        logger.info(f"Profile {business_id} final enable_ai_faq_auto_reply state in DB: {profile.enable_ai_faq_auto_reply}")
        return BusinessProfile.from_orm(profile)
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating business profile {business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update business profile.")

@router.get("/{business_id}/timezone", response_model=dict)
def get_business_timezone(business_id: int, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")
    return {"timezone": profile.timezone}

@router.put("/{business_id}/timezone", response_model=dict)
def update_business_timezone(business_id: int, timezone_payload: dict, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")
    
    new_timezone = timezone_payload.get("timezone")
    if new_timezone is None or not isinstance(new_timezone, str):
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or missing 'timezone' string in payload.")
    
    profile.timezone = new_timezone
    try:
        db.commit()
        return {"timezone": profile.timezone}
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating timezone for business {business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update timezone.")

@router.get("/business-id/{business_name}", response_model=dict)
def get_business_id_by_name(business_name: str, db: Session = Depends(get_db)):
    business = db.query(BusinessProfileModel.id).filter(BusinessProfileModel.business_name == business_name).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with name '{business_name}' not found")
    return {"business_id": business.id}

@router.get("/business-id/slug/{slug}", response_model=dict)
async def get_business_id_by_slug(slug: str, db: Session = Depends(get_db)):
    logger.info(f"Attempting to fetch business ID with slug: {slug}")
    try:
        business = db.query(BusinessProfileModel.id).filter(BusinessProfileModel.slug == slug).first()
        if not business:
            logger.warning(f"No business found with slug: {slug}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with slug '{slug}' not found")
        logger.info(f"Successfully found business with ID: {business.id} for slug: {slug}")
        return {"business_id": business.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching business ID by slug '{slug}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching business ID by slug"
        )

@router.get("/navigation-profile/slug/{slug}", response_model=BusinessProfile)
async def get_navigation_profile_by_slug(slug: str, db: Session = Depends(get_db)):
    logger.info(f"Attempting to fetch navigation profile (full) with slug: {slug}")
    try:
        business = db.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first()
        if not business:
            logger.warning(f"No business found for navigation profile with slug: {slug}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found for this slug (for navigation)")
        logger.info(f"Successfully found navigation profile for slug {slug}: ID {business.id}, Name: {business.business_name}")
        return BusinessProfile.from_orm(business)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching navigation profile by slug {slug}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching navigation profile by slug"
        )

@router.patch("/{business_id}/phone", response_model=BusinessProfile)
def update_business_phone(
    business_id: int,
    phone_update: BusinessPhoneUpdate,
    db: Session = Depends(get_db)
):
    business = db.query(BusinessProfileModel).filter(
        BusinessProfileModel.id == business_id
    ).first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found"
        )
    
    business.business_phone_number = phone_update.business_phone_number
    try:
        db.commit()
        db.refresh(business)
        return BusinessProfile.from_orm(business)
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating business phone for business ID {business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update phone number.")

@router.delete("/abandoned", response_model=dict)
def cleanup_abandoned_profiles(db: Session = Depends(get_db)):
    cutoff_date = datetime.utcnow() - timedelta(days=7)
    
    query = db.query(BusinessProfileModel).filter(
        BusinessProfileModel.business_phone_number.is_(None),
        BusinessProfileModel.created_at < cutoff_date
    )
    try:
        num_deleted = query.delete(synchronize_session=False)
        db.commit()
        if num_deleted > 0:
            logger.info(f"Deleted {num_deleted} abandoned profiles.")
        else:
            logger.info("No abandoned profiles to delete.")
        return {"message": f"Deleted {num_deleted} abandoned profiles"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error during cleanup of abandoned profiles: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cleanup abandoned profiles.")