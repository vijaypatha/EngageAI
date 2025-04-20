from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.database import get_db
from app.models import Customer, BusinessProfile, ConsentLog
from app.schemas import CustomerCreate, CustomerUpdate
from app.services.sms_optin import send_double_optin_sms

router = APIRouter()

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
        business_id=customer.business_id
    )
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    send_double_optin_sms(new_customer.id)
    return new_customer

# 📦 Get all customers under a business
@router.get("/by-business/{business_id}", summary="List customers by business")
def get_customers_by_business(business_id: int, db: Session = Depends(get_db)):
    subquery = (
        db.query(
            ConsentLog.customer_id,
            func.max(ConsentLog.replied_at).label("latest_reply"),
            ConsentLog.status
        )
        .filter(ConsentLog.business_id == business_id)
        .group_by(ConsentLog.customer_id, ConsentLog.status)
        .subquery()
    )

    results = (
        db.query(Customer, subquery.c.status.label("latest_consent_status"))
        .outerjoin(subquery, Customer.id == subquery.c.customer_id)
        .filter(Customer.business_id == business_id)
        .all()
    )

    return [
        {**customer.__dict__, "latest_consent_status": consent_status}
        for customer, consent_status in results
    ]

# 🔍 Get specific customer
@router.get("/{customer_id}", summary="Get customer")
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

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
