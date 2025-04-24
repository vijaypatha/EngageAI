from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from app.database import get_db
from app.models import Customer, BusinessProfile, ConsentLog
from app.schemas import CustomerCreate, CustomerUpdate
from app.services.sms_optin import send_double_optin_sms
from datetime import datetime
from typing import Optional

router = APIRouter()

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

def validate_consent_status(customer: Customer, status: Optional[str]) -> bool:
    """Validate that the customer's opted_in status matches their latest consent status."""
    if not status:
        return not customer.opted_in  # Should be False if no consent log
        
    return (
        (status == "opted_in" and customer.opted_in) or
        (status == "opted_out" and not customer.opted_in) or
        (status in ["pending", "waiting"])
    )

# ➕ Add Customer (during or post-onboarding)
@router.post("", summary="Add customer")
def add_customer(customer: CustomerCreate, db: Session = Depends(get_db)):
    print(f"📥 POST /customers/ hit with business_id={customer.business_id}")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    new_customer = Customer(
        customer_name=customer.customer_name,
        phone=customer.phone,
        lifecycle_stage=customer.lifecycle_stage,
        pain_points=customer.pain_points,
        interaction_history=customer.interaction_history,
        business_id=customer.business_id,
        timezone=customer.timezone
    )

    db.add(new_customer)
    try:
        db.commit()
        db.refresh(new_customer)
    except Exception as e:
        db.rollback()
        import traceback
        print(f"❌ Error creating customer: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error while creating customer")

    # Validate and send opt-in SMS
    if not business.twilio_number or not new_customer.phone:
        db.delete(new_customer)
        db.commit()
        raise HTTPException(status_code=400, detail="Missing phone number or Twilio number.")
    if business.twilio_number == new_customer.phone:
        db.delete(new_customer)
        db.commit()
        raise HTTPException(status_code=400, detail="Customer phone number cannot be the same as your Twilio number.")
    if not new_customer.phone.startswith("+") or len(new_customer.phone) < 10:
        db.delete(new_customer)
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid phone number format. Use E.164 format like +1234567890.")

    try:
        send_double_optin_sms(new_customer.id)
    except Exception as sms_err:
        db.delete(new_customer)
        db.commit()
        raise HTTPException(status_code=400, detail=f"Twilio error while sending SMS: {sms_err}")

    return new_customer

# 📦 Get all customers under a business
@router.get("/by-business/{business_id}", summary="List customers by business")
def get_customers_by_business(business_id: int, db: Session = Depends(get_db)):
    # Get all customers for the business
    customers = db.query(Customer).filter(Customer.business_id == business_id).all()
    
    result = []
    for customer in customers:
        # Get latest consent status
        latest_status, latest_updated = get_latest_consent_status(customer.id, db)
        
        # Validate consent status consistency
        if not validate_consent_status(customer, latest_status):
            print(f"Warning: Inconsistent consent status for customer {customer.id}")
            # Attempt to fix inconsistency
            if latest_status == "opted_in":
                customer.opted_in = True
            elif latest_status == "opted_out":
                customer.opted_in = False
            db.commit()
        
        result.append({
            **customer.__dict__,
            "latest_consent_status": latest_status,
            "latest_consent_updated": latest_updated.isoformat() if latest_updated else None
        })
    
    return result

# 🔍 Get specific customer
@router.get("/{customer_id}", summary="Get customer")
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
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
    
    return {
        **customer.__dict__,
        "latest_consent_status": latest_status,
        "latest_consent_updated": latest_updated.isoformat() if latest_updated else None
    }

# ✏️ Update customer
@router.put("/{customer_id}", summary="Update customer")
def update_customer(customer_id: int, customer: CustomerUpdate, db: Session = Depends(get_db)):
    db_customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not db_customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    for field, value in customer.dict(exclude_unset=True).items():
        setattr(db_customer, field, value)
    db.commit()
    db.refresh(db_customer)
    return db_customer

# 🚗️ Delete customer
@router.delete("/{customer_id}", summary="Delete customer")
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    try:
        # Start a transaction
        # First, delete all consent logs for this customer
        db.query(ConsentLog).filter(ConsentLog.customer_id == customer_id).delete()
        
        # Then delete the customer
        result = db.query(Customer).filter(Customer.id == customer_id).delete()
        if not result:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Commit the transaction
        db.commit()
        return {"message": "Customer deleted successfully"}
    except Exception as e:
        db.rollback()
        print(f"Error deleting customer: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
