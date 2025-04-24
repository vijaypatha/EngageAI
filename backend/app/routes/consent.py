from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from app.database import get_db
from app.models import ConsentLog, Customer

router = APIRouter()

class ConsentStatusResponse(BaseModel):
    customer_id: int
    status: str
    opted_in: bool
    last_updated: Optional[datetime]
    method: Optional[str]

@router.get("/status/{customer_id}")
def get_consent_status(customer_id: int, db: Session = Depends(get_db)):
    # First check if customer exists
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get latest consent log
    latest_consent = (
        db.query(ConsentLog)
        .filter(ConsentLog.customer_id == customer_id)
        .order_by(ConsentLog.replied_at.desc())
        .first()
    )
    
    return {
        "customer_id": customer_id,
        "status": latest_consent.status if latest_consent else "pending",
        "last_updated": latest_consent.replied_at.isoformat() if latest_consent and latest_consent.replied_at else None,
        "opted_in": customer.opted_in
    }