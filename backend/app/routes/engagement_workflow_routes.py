# File: engagement_workflow_routes.py
# Link: /Users/vijaypatha/Developer/FastAPI/EngageAI/backend/app/routes/engagement_workflow_routes.py
#
# BUSINESS OWNER PERSPECTIVE:
# This file handles the workflow for managing customer engagements, including
# sending SMS messages, tracking responses, and updating engagement status.

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Engagement, Customer, BusinessProfile
from app.services.twilio_service import send_sms_via_twilio  
from datetime import datetime
from pydantic import BaseModel

router = APIRouter()

@router.get("/")
def get_engagement_stats(db: Session = Depends(get_db)):
    total_responses = db.query(Engagement).count()
    return {"total_responses": total_responses}

@router.put("/reply/{id}/edit")
def update_ai_response(id: int, payload: dict, db: Session = Depends(get_db)):
    new_ai_response = payload.get("ai_response")
    if not new_ai_response:
        raise HTTPException(status_code=400, detail="Missing ai_response")

    engagement = db.query(Engagement).filter(Engagement.id == id).first()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    engagement.ai_response = new_ai_response
    db.commit()
    return {"message": "AI response updated successfully."}

@router.put("/reply/{id}/send")
def send_reply(id: int, db: Session = Depends(get_db)):
    # 1. Fetch the engagement
    engagement = db.query(Engagement).filter(Engagement.id == id).first()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    # 2. Validate engagement status
    if engagement.status != "pending_review":
        raise HTTPException(status_code=400, detail="Already processed")

    # 3. Fetch customer details
    customer = db.query(Customer).filter(Customer.id == engagement.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if not customer.phone:
        raise HTTPException(status_code=400, detail="Customer phone number is missing")

    # 3.5 Fetch business details
    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # 4. Send SMS using Twilio
    try:
        send_sms_via_twilio(to=customer.phone, message=engagement.ai_response, business=business)
    except Exception as e:
        print(f"❌ Twilio send failed: {e}")  # <== This line will log the exact cause
        raise HTTPException(status_code=500, detail=f"Failed to send SMS: {str(e)}")

    # 5. Mark as sent
    engagement.status = "sent"
    engagement.sent_at = datetime.utcnow()
    db.commit()
    return {"message": "Reply sent successfully"}

class ManualReplyPayload(BaseModel):
    message: str

@router.post("/manual-reply/{customer_id}")
async def send_manual_reply(customer_id: int, payload: ManualReplyPayload, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    try:
        await send_sms_via_twilio(to=customer.phone, message=payload.message, business=business)
    except Exception as e:
        print(f"❌ Twilio send failed for manual reply: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send SMS: {str(e)}")

    new_engagement = Engagement(
        customer_id=customer_id,
        ai_response=payload.message,  # Consider renaming this field or using a different one for manual messages
        status="sent",
        sent_at=datetime.utcnow()
    )
    db.add(new_engagement)
    db.commit()
    return {"message": "Manual reply sent and saved successfully."}


@router.put("/{id}/edit-ai-draft", summary="Update the AI response draft for an engagement")
def update_ai_draft(
    id: int,
    payload: dict = Body(..., example={"draft": "Your draft message here"}),
    db: Session = Depends(get_db)
):
    """
    Update the AI response draft for a specific engagement.

    - **id**: The engagement ID.
    - **payload**: JSON with either 'draft' or 'ai_response' as the new draft text.

    Returns: {"status": "updated"}
    """
    engagement = db.query(Engagement).filter(Engagement.id == id).first()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    new_draft = payload.get("draft") or payload.get("ai_response")
    if not new_draft:
        raise HTTPException(status_code=400, detail="Missing draft or ai_response in payload")

    engagement.ai_response = new_draft
    db.commit()
    return {"status": "updated"}