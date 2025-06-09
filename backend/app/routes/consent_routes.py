# API endpoints for managing customer consent and communication preferences
# Business owners can track who has opted in/out of receiving messages and view consent history
from fastapi import APIRouter, Depends, HTTPException, status, Path
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ConsentLog, Customer, BusinessProfile
from app.schemas import ConsentCreate, ConsentResponse
from app.services.consent_service import ConsentService
from typing import List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["consent"]
)

def get_consent_service(db: Session = Depends(get_db)) -> ConsentService:
    return ConsentService(db)

@router.post("/opt-in", response_model=ConsentResponse)
async def opt_in(
    consent: ConsentCreate,
    consent_service: ConsentService = Depends(get_consent_service),
    db: Session = Depends(get_db)
):
    """Handle customer opt-in"""
    try:
        consent_log = await consent_service.handle_opt_in(
            phone_number=consent.phone_number,
            business_id=consent.business_id,
            customer_id=consent.customer_id
        )
        return ConsentResponse.model_validate(consent_log)
    except Exception as e:
        logger.error(f"Error processing opt-in: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/opt-out", response_model=ConsentResponse)
async def opt_out(
    consent: ConsentCreate,
    consent_service: ConsentService = Depends(get_consent_service),
    db: Session = Depends(get_db)
):
    """Handle customer opt-out"""
    try:
        consent_log = await consent_service.handle_opt_out(
            phone_number=consent.phone_number,
            business_id=consent.business_id,
            customer_id=consent.customer_id
        )
        return ConsentResponse.model_validate(consent_log)
    except Exception as e:
        logger.error(f"Error processing opt-out: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/status/{phone_number}/{business_id}")
async def check_consent_status(
    phone_number: str,
    business_id: int,
    consent_service: ConsentService = Depends(get_consent_service),
    db: Session = Depends(get_db)
):
    """Check if a customer has opted in"""
    try:
        has_consent = await consent_service.check_consent(
            phone_number=phone_number,
            business_id=business_id
        )
        return {"has_consent": has_consent}
    except Exception as e:
        logger.error(f"Error checking consent status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/logs/{business_id}", response_model=List[ConsentResponse])
async def get_consent_logs(
    business_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get consent logs for a business"""
    logs = db.query(ConsentLog).filter(
        ConsentLog.business_id == business_id
    ).offset(skip).limit(limit).all()
    return [ConsentResponse.model_validate(log) for log in logs]

@router.post("/resend-optin/{customer_id}")
async def resend_opt_in(
    customer_id: int = Path(..., description="The ID of the customer to resend opt-in to"),
    consent_service: ConsentService = Depends(get_consent_service),
    db: Session = Depends(get_db)
):
    """
    Resend the opt-in SMS to a customer.
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    try:
        await consent_service.send_opt_in_sms(
            phone_number=customer.phone,
            business_id=business.id,
            customer_id=customer.id
        )
        return {"message": "Opt-in request resent successfully"}
    except Exception as e:
        logger.error(f"Failed to resend opt-in: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to resend opt-in request")

