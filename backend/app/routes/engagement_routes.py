from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Engagement as EngagementModel
from app.schemas import Engagement, EngagementCreate, EngagementUpdate
from typing import List
from ..auth import get_current_user

router = APIRouter(
    tags=["engagements"]
)

@router.post("/", response_model=Engagement)
def create_engagement(
    engagement: EngagementCreate,
    db: Session = Depends(get_db),
    current_user: Engagement = Depends(get_current_user)
):
    db_engagement = EngagementModel(**engagement.model_dump())
    db.add(db_engagement)
    db.commit()
    db.refresh(db_engagement)
    return Engagement.from_orm(db_engagement)

@router.get("/", response_model=List[Engagement])
def get_engagements(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    engagements = db.query(EngagementModel).offset(skip).limit(limit).all()
    return [Engagement.from_orm(engagement) for engagement in engagements]

@router.get("/{engagement_id}", response_model=Engagement)
def get_engagement(engagement_id: int, db: Session = Depends(get_db)):
    engagement = db.query(EngagementModel).filter(EngagementModel.id == engagement_id).first()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return Engagement.from_orm(engagement)

@router.put("/{engagement_id}", response_model=Engagement)
def update_engagement(
    engagement_id: int,
    engagement: EngagementUpdate,
    db: Session = Depends(get_db)
):
    db_engagement = db.query(EngagementModel).filter(EngagementModel.id == engagement_id).first()
    if not db_engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    
    for field, value in engagement.model_dump(exclude_unset=True).items():
        setattr(db_engagement, field, value)
    
    db.commit()
    db.refresh(db_engagement)
    return Engagement.from_orm(db_engagement)

@router.delete("/{engagement_id}")
def delete_engagement(engagement_id: int, db: Session = Depends(get_db)):
    engagement = db.query(EngagementModel).filter(EngagementModel.id == engagement_id).first()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    
    db.delete(engagement)
    db.commit()
    return {"message": "Engagement deleted successfully"} 