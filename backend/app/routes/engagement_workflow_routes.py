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
from app.config import settings
from app.services.twilio_service import send_sms_via_twilio  
from datetime import datetime
from pydantic import BaseModel
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

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

from pydantic import BaseModel

class SendDraftInput(BaseModel):
    updated_content: str

@router.put("/reply/{id}/send")
def send_reply(
    id: int,
    payload: SendDraftInput,
    db: Session = Depends(get_db)
):
    engagement = db.query(Engagement).filter(Engagement.id == id).first()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    if engagement.status != "pending_review" or engagement.sent_at is not None:
        raise HTTPException(
            status_code=400,
            detail="Draft not valid for sending (already sent or corrupted)."
        )

    message_content = payload.updated_content.strip()
    if not message_content:
        raise HTTPException(status_code=400, detail="Updated message content is empty")

    engagement.ai_response = message_content

    customer = db.query(Customer).filter(Customer.id == engagement.customer_id).first()
    if not customer or not customer.phone:
        raise HTTPException(status_code=404, detail="Customer not found or missing phone")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found for this customer")

    if not all([
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_AUTH_TOKEN,
        settings.TWILIO_FROM_NUMBER
    ]):
        raise HTTPException(status_code=500, detail="SMS provider is not configured")

    twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    try:
        print(f"📤 Sending updated AI draft to {customer.phone}")
        engagement.sent_at = None  # Clear leftover timestamp from broken draft creation
        message = twilio_client.messages.create(
            body=message_content,
            from_=settings.TWILIO_FROM_NUMBER,
            to=customer.phone
        )

        if message.status in ['failed', 'undelivered']:
            raise TwilioRestException(
                status=500,
                uri=message.uri,
                msg=f"Twilio reported message status: {message.status}. Error: {message.error_message}"
            )

        engagement.status = "sent"
        engagement.sent_at = datetime.utcnow()
        db.commit()
        db.refresh(engagement)

        return {
            "message": "Draft reply sent successfully",
            "engagement_id": engagement.id,
            "status": engagement.status,
            "sms_sid": message.sid
        }

    except TwilioRestException as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Twilio error: {e.msg}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

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


# Delete engagement draft route
from fastapi import status

@router.delete("/{engagement_id}", summary="Delete an engagement draft")
def delete_engagement_draft(engagement_id: int, db: Session = Depends(get_db)):
    """
    Delete an engagement draft by ID. Only allowed if the engagement is still in 'pending_review' state.
    """
    engagement = db.query(Engagement).filter(Engagement.id == engagement_id).first()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    if engagement.status != "pending_review":
        raise HTTPException(status_code=400, detail="Only drafts can be deleted")

    db.delete(engagement)
    db.commit()
    return {"message": "Engagement draft deleted successfully."}