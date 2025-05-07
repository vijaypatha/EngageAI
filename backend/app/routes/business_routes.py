# File: business_routes.py
# Link: backend/app/routes/business_routes.py
#
# BUSINESS OWNER PERSPECTIVE:
# This file manages all aspects of your business profile in the EngageAI platform, 
# from initial creation during onboarding to ongoing management. It stores critical information
# about your business including name, industry, goals, services, and timezone settings.
# This information is used throughout the system to personalize your AI messaging, ensure
# proper timing of communications, and maintain your brand identity in customer interactions.
#
# DEVELOPER PERSPECTIVE:
# Routes:
# - POST / - Creates new business profile during onboarding
# - GET /{business_id} - Retrieves business profile by ID
# - PUT /{business_id} - Updates business profile information
# - GET|PUT /{business_id}/timezone - Gets/sets timezone
# - GET /business-id/{business_name} - Looks up business ID by name
# - GET /business-id/slug/{slug} - Looks up business ID by slug (URL-friendly name)
# - PATCH /{business_id}/phone - Updates business phone number
# - DELETE /abandoned - Maintenance endpoint to clean up abandoned profiles
#
# Frontend Usage:
# - Initial profile creation in onboarding flow (frontend/src/app/onboarding/page.tsx)
# - Profile editing in profile pages (frontend/src/app/profile/[business_name]/page.tsx)
# - Referenced in dashboard (frontend/src/app/dashboard/[business_name]/page.tsx)
# - Business timezone management (frontend/src/app/business/profile/page.tsx)
#
# Uses slugify() helper to generate URL-friendly business names
# Implements get_current_user auth dependency for some routes

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BusinessProfile as BusinessProfileModel
from app.schemas import BusinessProfile, BusinessProfileCreate, BusinessProfileUpdate, BusinessPhoneUpdate, SMSStyleInput
import re
import logging
from typing import List
from ..auth import get_current_user
from datetime import datetime, timedelta
import uuid

# Configure logger
logger = logging.getLogger(__name__)

def slugify(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]+', '-', name.strip().lower())

router = APIRouter(
    tags=["business"]
)

# ➕ Create Business Profile (during onboarding)
@router.post("/", response_model=BusinessProfile)
def create_business_profile(
    business: BusinessProfileCreate,
    db: Session = Depends(get_db)
):
    # Check if business name already exists
    existing_business = db.query(BusinessProfileModel).filter(
        BusinessProfileModel.business_name == business.business_name
    ).first()
    if existing_business:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Business name already exists"
        )

    # Create slug from business name
    slug = slugify(business.business_name)
    
    # Create business profile
    db_business = BusinessProfileModel(
        **business.model_dump(),
        slug=slug
    )
    db.add(db_business)
    db.commit()
    db.refresh(db_business)
    return BusinessProfile.from_orm(db_business)

# 🔍 Get Business Profile by ID
@router.get("/{business_id}", response_model=BusinessProfile)
def get_business_profile(business_id: int, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return BusinessProfile.from_orm(profile)

# ✏️ Update Business Profile (post-onboarding)
@router.put("/{business_id}", response_model=BusinessProfile)
def update_business_profile(business_id: int, update: BusinessProfileUpdate, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Business profile not found")

    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return BusinessProfile.from_orm(profile)

# Get business timezone
@router.get("/{business_id}/timezone")
def get_business_timezone(business_id: int, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return {"timezone": profile.timezone}

# Update business timezone
@router.put("/{business_id}/timezone")
def update_business_timezone(business_id: int, timezone: dict, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Business profile not found")
    
    profile.timezone = timezone.get("timezone", "UTC")
    db.commit()
    return {"timezone": profile.timezone}

#  endpoint to get the business_id using the business_name
@router.get("/business-id/{business_name}")
def get_business_id_by_name(business_name: str, db: Session = Depends(get_db)):
    business = db.query(BusinessProfileModel).filter(BusinessProfileModel.business_name == business_name).first()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    return {"business_id": business.id}

@router.get("/business-id/slug/{slug}")
async def get_business_id_by_slug(slug: str, db: Session = Depends(get_db)):
    logger.info(f"Attempting to fetch business with slug: {slug}")
    try:
        business = db.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first()
        if not business:
            logger.warning(f"No business found with slug: {slug}")
            raise HTTPException(status_code=404, detail="Business not found")
        logger.info(f"Successfully found business with ID: {business.id}")
        return {"business_id": business.id}
    except Exception as e:
        logger.error(f"Error fetching business by slug: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while fetching business"
        )

@router.patch("/{business_id}/phone", response_model=BusinessProfile)
def update_business_phone(
    business_id: int,
    phone_update: BusinessPhoneUpdate,
    db: Session = Depends(get_db),
    current_user: BusinessProfile = Depends(get_current_user)
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
    db.commit()
    db.refresh(business)
    return BusinessProfile.from_orm(business)

@router.delete("/abandoned")
def cleanup_abandoned_profiles(db: Session = Depends(get_db)):
    """Delete business profiles that have been abandoned (created over 7 days ago without a phone number)"""
    cutoff_date = datetime.utcnow() - timedelta(days=7)
    
    abandoned_profiles = db.query(BusinessProfileModel).filter(
        BusinessProfileModel.business_phone_number == None,
        BusinessProfileModel.created_at < cutoff_date
    ).all()
    
    for profile in abandoned_profiles:
        db.delete(profile)
    
    db.commit()
    return {"message": f"Deleted {len(abandoned_profiles)} abandoned profiles"}

# NEW Endpoint for Navigation Data
@router.get("/navigation-profile/slug/{slug}", response_model=BusinessProfile)
async def get_navigation_profile_by_slug(slug: str, db: Session = Depends(get_db)):
    logger.info(f"Attempting to fetch navigation profile with slug: {slug}")
    try:
        business = db.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first()
        if not business:
            logger.warning(f"No business found for navigation profile with slug: {slug}")
            # Return a default structure or raise 404.
            # For navigation, it's often better to provide defaults if the main app should still load.
            # However, if the slug is essential for all nav links, a 404 might be appropriate.
            # Let's raise 404 for now, consistent with other lookups.
            raise HTTPException(status_code=404, detail="Business profile not found for this slug (for navigation)")
        
        logger.info(f"Successfully found navigation profile for slug {slug}: {business.business_name}")
        # Convert the SQLAlchemy model instance to a Pydantic model instance
        return BusinessProfile.from_orm(business)
    except HTTPException:
        raise # Re-raise HTTPExceptions directly
    except Exception as e:
        logger.error(f"Error fetching navigation profile by slug {slug}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while fetching navigation profile by slug"
        )
