# backend/app/routes/engagement_routes.py

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_async_db
# Corrected: Import 'auth' module and then use 'auth.get_current_authenticated_business'
from app import models, schemas, auth
# from app.models import User as UserModel # This import is no longer needed for auth
from app.config import Settings, get_settings # If settings are needed for other purposes

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Engagements"]
)

# Helper function to check if engagement belongs to the business
async def get_engagement_for_business(
    engagement_id: int,
    business_id: int,
    db: AsyncSession
) -> Optional[models.Engagement]:
    stmt = select(models.Engagement).where(
        models.Engagement.id == engagement_id,
        models.Engagement.business_id == business_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.post("/", response_model=schemas.EngagementRead, status_code=status.HTTP_201_CREATED)
async def create_engagement(
    engagement_data: schemas.EngagementCreate,
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business)
):
    logger.info(f"Engagement Create: Attempt by Business ID {current_business.id} for customer {engagement_data.customer_id}")

    if engagement_data.business_id != current_business.id:
        logger.warning(
            f"Engagement Create AuthZ Error: Auth Business ID {current_business.id} "
            f"does not match payload business_id {engagement_data.business_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create engagement for another business."
        )

    customer = await db.get(models.Customer, engagement_data.customer_id)
    if not customer or customer.business_id != current_business.id:
        logger.warning(f"Engagement Create: Customer {engagement_data.customer_id} not found or not part of business {current_business.id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found for this business.")

    db_engagement = models.Engagement(**engagement_data.model_dump())
    # If Engagement model has a field like `created_by_owner_id` or similar to link to the User table
    # and current_business.owner_id holds that user ID, you can set it here:
    # if hasattr(db_engagement, 'created_by_user_id') and current_business.owner_id:
    #     db_engagement.created_by_user_id = current_business.owner_id
    
    db.add(db_engagement)
    await db.commit()
    await db.refresh(db_engagement)
    
    logger.info(f"Engagement Create: Successfully created engagement ID {db_engagement.id} for Business ID {current_business.id}")
    return db_engagement


@router.get("/", response_model=List[schemas.EngagementRead])
async def list_engagements(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=0, le=500),
    customer_id: Optional[int] = Query(None, description="Filter engagements by customer ID"),
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business)
):
    logger.info(f"Engagement List: Request by Business ID {current_business.id}, Customer Filter: {customer_id}")
    
    stmt = select(models.Engagement).where(models.Engagement.business_id == current_business.id)
    
    if customer_id is not None:
        stmt = stmt.where(models.Engagement.customer_id == customer_id)
        customer = await db.get(models.Customer, customer_id)
        if not customer or customer.business_id != current_business.id:
            logger.warning(f"Engagement List: Attempt to filter by customer {customer_id} not belonging to business {current_business.id}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid customer filter for this business.")
            
    stmt = stmt.offset(skip).limit(limit).order_by(models.Engagement.created_at.desc())
    
    result = await db.execute(stmt)
    engagements = result.scalars().all()
    
    logger.info(f"Engagement List: Found {len(engagements)} engagements for Business ID {current_business.id}")
    return engagements


@router.get("/{engagement_id}", response_model=schemas.EngagementRead)
async def get_engagement(
    engagement_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business)
):
    logger.info(f"Engagement Get: Request for ID {engagement_id} by Business ID {current_business.id}")
    
    engagement = await get_engagement_for_business(engagement_id, current_business.id, db)
    if not engagement:
        logger.warning(f"Engagement Get: Engagement ID {engagement_id} not found for Business ID {current_business.id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")
    
    logger.info(f"Engagement Get: Successfully retrieved engagement ID {engagement.id}")
    return engagement


@router.put("/{engagement_id}", response_model=schemas.EngagementRead)
async def update_engagement(
    engagement_id: int,
    engagement_data: schemas.EngagementUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business)
):
    logger.info(f"Engagement Update: Request for ID {engagement_id} by Business ID {current_business.id}")
    
    db_engagement = await get_engagement_for_business(engagement_id, current_business.id, db)
    if not db_engagement:
        logger.warning(f"Engagement Update: Engagement ID {engagement_id} not found for Business ID {current_business.id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    update_data = engagement_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_engagement, field, value)
    
    if 'business_id' in update_data and update_data['business_id'] != current_business.id:
        logger.error(f"Engagement Update AuthZ Error: Attempt to change business_id for engagement {engagement_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot change business association of an engagement.")
    
    if 'customer_id' in update_data:
        new_customer_id = update_data['customer_id']
        customer = await db.get(models.Customer, new_customer_id)
        if not customer or customer.business_id != current_business.id:
            logger.warning(f"Engagement Update: New customer {new_customer_id} not found or not part of business {current_business.id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid customer ID for this business.")

    await db.commit()
    await db.refresh(db_engagement)
    
    logger.info(f"Engagement Update: Successfully updated engagement ID {db_engagement.id}")
    return db_engagement


@router.delete("/{engagement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_engagement(
    engagement_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business)
):
    logger.info(f"Engagement Delete: Request for ID {engagement_id} by Business ID {current_business.id}")
    
    engagement = await get_engagement_for_business(engagement_id, current_business.id, db)
    if not engagement:
        logger.warning(f"Engagement Delete: Engagement ID {engagement_id} not found for Business ID {current_business.id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")
    
    await db.delete(engagement)
    await db.commit()
    
    logger.info(f"Engagement Delete: Successfully deleted engagement ID {engagement_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)