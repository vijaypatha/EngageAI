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

@router.get("/consent-status/{customer_id}", response_model=ConsentStatusResponse)
async def get_consent_status(
    customer_id: int,
    db: Session = Depends(get_db)
):
    """
    Get the current consent status for a customer by checking their latest ConsentLog entry
    and Customer.opted_in field.
    """
    # Get the customer
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Get the latest consent log using the new index
    latest_consent = (
        db.query(ConsentLog)
        .filter(ConsentLog.customer_id == customer_id)
        .order_by(desc(ConsentLog.replied_at))
        .first()
    )

    if not latest_consent:
        return ConsentStatusResponse(
            customer_id=customer_id,
            status="pending",
            opted_in=False,
            last_updated=None,
            method=None
        )

    return ConsentStatusResponse(
        customer_id=customer_id,
        status=latest_consent.status,
        opted_in=customer.opted_in or False,
        last_updated=latest_consent.replied_at,
        method=latest_consent.method
    )