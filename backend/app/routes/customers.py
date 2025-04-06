### ✅ customers.py

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Customer, BusinessProfile
from app.schemas import CustomerCreate, CustomerUpdate

router = APIRouter()

# ➕ Add Customer (during or post-onboarding)
@router.post("", summary="Add customer")
def add_customer(customer: CustomerCreate, db: Session = Depends(get_db), business_id: int = Header(..., alias="business-Id")):
    print(f"📥 POST /customers/ hit with business_id={business_id}")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    new_customer = Customer(
        customer_name=customer.customer_name,
        phone=customer.phone,
        lifecycle_stage=customer.lifecycle_stage,
        pain_points=customer.pain_points,
        interaction_history=customer.interaction_history,
        business_id=business.id
    )
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    return new_customer

# 📦 Get all customers under a business
@router.get("/by-business/{business_id}", summary="List customers by business")
def get_customers_by_business(business_id: int, db: Session = Depends(get_db)):
    return db.query(Customer).filter(Customer.business_id == business_id).all()

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

# 🗑️ Delete customer
@router.delete("/{customer_id}", summary="Delete customer")
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    db_customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not db_customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    db.delete(db_customer)
    db.commit()
    return {"message": "Customer deleted successfully"}