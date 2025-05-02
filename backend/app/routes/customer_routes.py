from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from app.database import get_db
from app.models import Customer as CustomerModel, BusinessProfile, ConsentLog
from app.schemas import Customer, CustomerCreate, CustomerUpdate
from app.services.consent_service import ConsentService
from datetime import datetime
from typing import Optional, List
from ..auth import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["customers"]
)

def get_latest_consent_status(customer_id: int, db: Session) -> tuple[Optional[str], Optional[datetime]]:
    """Get the latest consent status and timestamp for a customer."""
    latest_consent = (
        db.query(ConsentLog)
        .filter(ConsentLog.customer_id == customer_id)
        .order_by(desc(ConsentLog.replied_at))
        .first()
    )
    
    if not latest_consent:
        return None, None
        
    return latest_consent.status, latest_consent.replied_at

def validate_consent_status(customer: CustomerModel, status: Optional[str]) -> bool:
    """Validate that the customer's opted_in status matches their latest consent status."""
    if not status:
        return not customer.opted_in  # Should be False if no consent log
        
    return (
        (status == "opted_in" and customer.opted_in) or
        (status == "opted_out" and not customer.opted_in) or
        (status in ["pending", "waiting"])
    )

@router.post("/", response_model=Customer)
def create_customer(
    customer: CustomerCreate,
    db: Session = Depends(get_db),
):
    db_customer = CustomerModel(**customer.model_dump())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return Customer.from_orm(db_customer)

@router.get("/", response_model=List[Customer])
def get_customers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    customers = db.query(CustomerModel).offset(skip).limit(limit).all()
    return [Customer.from_orm(customer) for customer in customers]

@router.get("/{customer_id}", response_model=Customer)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get latest consent status
    latest_status, latest_updated = get_latest_consent_status(customer_id, db)
    
    # Validate consent status consistency
    if not validate_consent_status(customer, latest_status):
        print(f"Warning: Inconsistent consent status for customer {customer_id}")
        # Attempt to fix inconsistency
        if latest_status == "opted_in":
            customer.opted_in = True
        elif latest_status == "opted_out":
            customer.opted_in = False
        db.commit()
    
    return Customer.from_orm(customer)

@router.put("/{customer_id}", response_model=Customer)
def update_customer(
    customer_id: int,
    customer: CustomerUpdate,
    db: Session = Depends(get_db)
):
    db_customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not db_customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    for field, value in customer.model_dump(exclude_unset=True).items():
        setattr(db_customer, field, value)
    
    db.commit()
    db.refresh(db_customer)
    return Customer.from_orm(db_customer)

@router.delete("/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    db.delete(customer)
    db.commit()
    return {"message": "Customer deleted successfully"}

# This endpoint fetches customers by business ID and adds consent info
@router.get("/by-business/{business_id}", response_model=List[Customer])
def get_customers_by_business(business_id: int, db: Session = Depends(get_db)):
    """
    Retrieves a list of customers associated with a specific business ID,
    including their latest consent status and timestamp.
    """
    logger.info(f"Fetching customers for business_id: {business_id}") # Assumes logger is defined

    # Query customers for the given business
    customers_orm = db.query(CustomerModel).filter(CustomerModel.business_id == business_id).all()

    if not customers_orm:
        logger.info(f"No customers found for business_id: {business_id}")
        return [] # Return empty list if no customers found

    customers_response = []
    for customer_orm in customers_orm:
        # Get latest consent status using the existing helper function
        latest_status, latest_updated = get_latest_consent_status(customer_orm.id, db)

        opted_in = latest_status == "opted_in" if latest_status else False

        # Create a dictionary from the ORM customer object
        # We do this manually to easily add the extra consent fields
        # before potentially validating against a Pydantic model
        customer_data = {
            "id": customer_orm.id,
            "customer_name": customer_orm.customer_name,
            "phone": customer_orm.phone,
            "lifecycle_stage": customer_orm.lifecycle_stage,
            "pain_points": customer_orm.pain_points,
            "interaction_history": customer_orm.interaction_history,
            "business_id": customer_orm.business_id,
            "timezone": customer_orm.timezone,
            "opted_in": opted_in,
            "is_generating_roadmap": customer_orm.is_generating_roadmap,
            "last_generation_attempt": customer_orm.last_generation_attempt,
            "created_at": customer_orm.created_at,
            "updated_at": customer_orm.updated_at,
            # Add the consent fields needed by the frontend
            "latest_consent_status": latest_status,
            "latest_consent_updated": latest_updated
        }
        # Append the dictionary (FastAPI will validate against response_model later)
        customers_response.append(customer_data)

    logger.info(f"Returning {len(customers_response)} customers for business_id: {business_id}")
    return customers_response