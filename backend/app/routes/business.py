from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BusinessProfile
from app.schemas import BusinessProfileCreate, BusinessProfileUpdate
import re

def slugify(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]+', '-', name.strip().lower())

router = APIRouter()

# ➕ Create Business Profile (during onboarding)
@router.post("/", summary="Create business profile")
def create_business_profile(profile: BusinessProfileCreate, db: Session = Depends(get_db)):
    print("📥 Hit /business-profile POST route")

    new_profile = BusinessProfile(
        business_name=profile.business_name,
        industry=profile.industry,
        business_goal=profile.business_goal,
        primary_services=profile.primary_services,
        representative_name=profile.representative_name
    )
    new_profile.slug = slugify(profile.business_name)
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    return {
        "id": new_profile.id,
        "slug": new_profile.slug,
        "business_name": new_profile.business_name
    }

# 🔍 Get Business Profile by ID
@router.get("/{business_id}", summary="Get business profile")
def get_business_profile(business_id: int, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return profile

# ✏️ Update Business Profile (post-onboarding)
@router.put("/{business_id}", summary="Update business profile")
def update_business_profile(business_id: int, update: BusinessProfileUpdate, db: Session = Depends(get_db)):
    profile = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Business profile not found")

    for field, value in update.dict(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile

#  endpoint to get the business_id using the business_name
@router.get("/business-id/{business_name}")
def get_business_id_by_name(business_name: str, db: Session = Depends(get_db)):
    business = db.query(BusinessProfile).filter(BusinessProfile.business_name == business_name).first()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    return {"business_id": business.id}

@router.get("/business-id/slug/{slug}")
def get_business_id_by_slug(slug: str, db: Session = Depends(get_db)):
    business = db.query(BusinessProfile).filter(BusinessProfile.slug == slug).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return {"business_id": business.id}