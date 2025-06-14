# backend/app/routes/business_routes.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import json
import re
import logging
from datetime import datetime, timedelta
from typing import Dict

from app.database import get_db
from app.models import BusinessProfile as BusinessProfileModel
from app.schemas import (
    BusinessProfile,
    BusinessProfileCreate,
    BusinessProfileUpdate,
    BusinessPhoneUpdate
)

logger = logging.getLogger(__name__)

def slugify(name: str) -> str:
    name_str = str(name) if name is not None else ""
    name_str = name_str.strip().lower()
    name_str = re.sub(r'\s+', '-', name_str)
    name_str = re.sub(r'[^a-z0-9-]', '', name_str)
    name_str = re.sub(r'-+', '-', name_str)
    return name_str.strip('-')

# --- FIX: Removed the redundant 'prefix' argument. ---
# The prefix is correctly defined once in main.py where this router is included.
router = APIRouter(
    tags=["Business Profile"]
)

@router.post("/", response_model=BusinessProfile, status_code=status.HTTP_201_CREATED)
def create_business_profile(
    business: BusinessProfileCreate,
    db: Session = Depends(get_db)
):
    if db.query(BusinessProfileModel).filter(BusinessProfileModel.business_name == business.business_name).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Business name already exists")

    slug = slugify(business.business_name)
    if db.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Generated slug '{slug}' already exists.")
        
    db_business = BusinessProfileModel(**business.model_dump(), slug=slug)
    try:
        db.add(db_business)
        db.commit()
        db.refresh(db_business)
        return db_business
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating business profile '{business.business_name}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create business profile.")

@router.get("/{business_id}", response_model=BusinessProfile)
def get_business_profile(business_id: int, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")
    return profile

@router.put("/{business_id}", response_model=BusinessProfile)
def update_business_profile(
    business_id: int,
    update_payload: BusinessProfileUpdate,
    db: Session = Depends(get_db)
):
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")

    update_data = update_payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided.")

    for field, value in update_data.items():
        setattr(profile, field, value)
    
    try:
        db.commit()
        db.refresh(profile)
        logger.info(f"Successfully updated business profile for ID: {business_id}")
        return profile
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating business profile {business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update business profile.")

@router.get("/business-id/slug/{slug}", response_model=dict)
def get_business_id_by_slug(slug: str, db: Session = Depends(get_db)):
    try:
        business = db.query(BusinessProfileModel.id).filter(BusinessProfileModel.slug == slug).first()
        if not business:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with slug '{slug}' not found")
        return {"business_id": business.id}
    except Exception as e:
        logger.error(f"Error fetching business ID by slug '{slug}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching business ID by slug")

@router.get("/navigation-profile/slug/{slug}")
def get_navigation_profile_by_slug(slug: str):
    """
    Placeholder endpoint to prevent 404 errors for navigation profiles.
    """
    logger.info(f"Placeholder hit for navigation profile with slug: {slug}")
    return JSONResponse(content={"slug": slug, "nav_items": []})

@router.get("/{business_id}/timezone", response_model=Dict[str, str])
def get_business_timezone(business_id: int, db: Session = Depends(get_db)):
    """
    Functional endpoint to fetch a business's timezone by its ID.
    """
    logger.info(f"Fetching timezone for business_id: {business_id}")
    business = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not business:
        logger.warning(f"Timezone requested for non-existent business_id: {business_id}")
        raise HTTPException(status_code=404, detail="Business not found")
    
    return {"timezone": business.timezone or "UTC"}