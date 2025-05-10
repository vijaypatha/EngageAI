# File: engagement_workflow_routes.py
# Link: /Users/vijaypatha/Developer/FastAPI/EngageAI/backend/app/routes/engagement_workflow_routes.py
#
# BUSINESS OWNER PERSPECTIVE:
# This file handles the workflow for managing customer engagements, including
# sending SMS messages, tracking responses, and updating engagement status.

import logging

from fastapi import APIRouter, Depends, HTTPException, Body, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Engagement, Customer, BusinessProfile
from app.config import settings
from app.services.twilio_service import send_sms_via_twilio  
from datetime import datetime
from pydantic import BaseModel
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


logger = logging.getLogger(__name__)

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
    logger.info(f"[SEND_REPLY] Querying engagement by ID {id}")
    engagement = db.query(Engagement).filter(Engagement.id == id).first()
    if not engagement:
        logger.warning(f"[SEND_REPLY] ❌ No engagement with ID {id}")
        raise HTTPException(status_code=404, detail="Engagement not found")
    
    logger.info(f"[SEND_REPLY] ✅ Engagement found: status={engagement.status}, customer_id={engagement.customer_id}")
    logger.info(f"[SEND_REPLY] 📦 Payload received: {payload}")

    if engagement.status.strip().lower() != "pending_review" or engagement.sent_at is not None:
        logger.warning(f"[BLOCKED] Draft not valid for sending — status: '{engagement.status}', sent_at: {engagement.sent_at}")
        raise HTTPException(
            status_code=409, # Conflict
            detail=f"Draft not valid for sending. Current status: '{engagement.status}', Sent at: {engagement.sent_at}"
        )

    message_content = payload.updated_content.strip()
    if not message_content:
        raise HTTPException(status_code=400, detail="Updated message content is empty")

    engagement.ai_response = message_content # Update draft content before sending

    customer = db.query(Customer).filter(Customer.id == engagement.customer_id).first()
    if not customer or not customer.phone:
        raise HTTPException(status_code=404, detail="Customer not found or missing phone")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
    if not business:
        logger.error(f"[SEND_REPLY] ❌ Business profile not found for business_id={customer.business_id}")
        raise HTTPException(status_code=500, detail="Business profile missing for customer")

    # Ensure the business has the necessary Twilio details
    if not business.messaging_service_sid:
        logger.error(f"[SEND_REPLY] ❌ Business profile (ID: {business.id}) is missing the Messaging Service SID.")
        raise HTTPException(status_code=500, detail="SMS Messaging Service ID is not configured for the business.")
    
    shared_messaging_service_sid = business.messaging_service_sid

    if not business.twilio_number: # This is the specific 'From' number
        logger.error(f"[SEND_REPLY] ❌ Business profile (ID: {business.id}) is missing its specific Twilio phone number (twilio_number).")
        raise HTTPException(status_code=500, detail="Sender phone number is not configured for this business.")
    
    specific_from_number = business.twilio_number

    if not all([
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_AUTH_TOKEN
    ]):
        logger.error("[SEND_REPLY] ❌ Twilio account credentials missing in settings.")
        raise HTTPException(status_code=500, detail="SMS provider account is not configured")

    twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    try:
        logger.info(f"[SEND_REPLY] 📤 Sending updated AI draft to {customer.phone} from {specific_from_number} via MS {shared_messaging_service_sid}")
        
        twilio_api_response = twilio_client.messages.create(
            body=message_content,
            messaging_service_sid=shared_messaging_service_sid, # Use the shared service SID
            from_=specific_from_number,                         # Use the business's specific 'From' number
            to=customer.phone
        )

        if twilio_api_response.status in ['failed', 'undelivered']:
            logger.error(f"[SEND_REPLY] Twilio reported message status: {twilio_api_response.status}. Error: {twilio_api_response.error_message} (SID: {twilio_api_response.sid})")
            # We will still update our DB to 'failed' but raise an error to frontend
            engagement.status = "failed_to_send" # Or a similar status
            engagement.message_metadata = {**(engagement.message_metadata or {}), 'twilio_error': twilio_api_response.error_message, 'twilio_sid': twilio_api_response.sid}
            db.commit()
            raise TwilioRestException( # Raise to be caught by the general TwilioRestException handler
                status=500, # Or map Twilio's error if available
                uri=twilio_api_response.uri,
                msg=f"Twilio reported message status: {twilio_api_response.status}. Error: {twilio_api_response.error_message}"
            )

        engagement.status = "sent"
        engagement.sent_at = datetime.utcnow()
        engagement.message_id = engagement.message_id # Keep existing link if any, or this could be source of original message
        engagement.message_metadata = {**(engagement.message_metadata or {}), 'twilio_sid': twilio_api_response.sid}

        db.commit()
        db.refresh(engagement)

        logger.info(f"[SEND_REPLY] ✅ Draft reply sent successfully. Engagement ID: {engagement.id}, New Status: {engagement.status}, SMS SID: {twilio_api_response.sid}")
        return {
            "message": "Draft reply sent successfully",
            "engagement_id": engagement.id,
            "status": engagement.status,
            "sms_sid": twilio_api_response.sid
        }

    except TwilioRestException as e:
        db.rollback() # Ensure rollback if commit hasn't happened or if error occurs after commit attempt
        logger.error(f"[SEND_REPLY] TwilioRestException: {e.status} - {e.msg}", exc_info=True)
        # Update engagement status to reflect failure if appropriate
        if engagement and engagement.status == "pending_review": # Check if not already updated by specific failure case
            engagement.status = "failed_to_send" # Or a generic "error" status
            engagement.message_metadata = {**(engagement.message_metadata or {}), 'twilio_error': e.msg}
            try:
                db.commit()
            except Exception as db_err:
                logger.error(f"[SEND_REPLY] Failed to update engagement status to failed after TwilioRestException: {db_err}")
                db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE if e.status >= 500 else status.HTTP_400_BAD_REQUEST, detail=f"Twilio error: {e.msg}")
    except Exception as e:
        db.rollback()
        logger.error(f"[SEND_REPLY] Unexpected Exception: {str(e)}", exc_info=True)
        if engagement and engagement.status == "pending_review":
            engagement.status = "failed_to_send"
            engagement.message_metadata = {**(engagement.message_metadata or {}), 'error': str(e)}
            try:
                db.commit()
            except Exception as db_err:
                logger.error(f"[SEND_REPLY] Failed to update engagement status to failed after Unexpected Exception: {db_err}")
                db.rollback()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

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
@router.delete("/{engagement_id}", summary="Clear an AI draft from an engagement")
def clear_engagement_ai_draft(engagement_id: int, db: Session = Depends(get_db)):
    """
    Clears the AI-generated draft response for an engagement by setting ai_response to None.
    The customer's original response and the engagement record itself remain.
    Only allowed if the engagement is in 'pending_review' status and has an ai_response.
    """
    logger.info(f"Attempting to clear AI draft for engagement_id: {engagement_id}")
    engagement = db.query(Engagement).filter(Engagement.id == engagement_id).first()

    if not engagement:
        logger.warning(f"DELETE /engagement-workflow/{engagement_id}: Engagement not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    # Check if there's an AI draft to clear
    if not engagement.ai_response:
        logger.info(f"DELETE /engagement-workflow/{engagement_id}: No AI draft to clear. ai_response is already null or empty.")
        # Return a success or specific message, as there's nothing to "delete"
        return {"message": "No AI draft to clear or it was already cleared.", "engagement_id": engagement_id}

    # Only allow clearing if it's truly a pending draft
    # Only allow clearing if it's a pending or dismissed draft
    allowed_statuses_for_clearing = ["pending_review", "dismissed"]
    if engagement.status not in allowed_statuses_for_clearing:
        logger.warning(f"DELETE /engagement-workflow/{engagement_id}: Attempt to clear AI draft for engagement with status '{engagement.status}'. Only statuses {allowed_statuses_for_clearing} allowed.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Only AI drafts for engagements in {allowed_statuses_for_clearing} status can be cleared. Current status: {engagement.status}")

    # --- THIS IS THE FIX ---
    engagement.ai_response = None  # Set the ai_response field to None (or an empty string if your DB/model prefers)
    # engagement.status = "customer_replied" # Optionally, change status to indicate manual review needed again, or create a new specific status
                                          # If you keep it 'pending_review', the UI will just show no draft.
    
    try:
        db.commit()
        db.refresh(engagement)
        logger.info(f"DELETE /engagement-workflow/{engagement_id}: AI draft cleared successfully. Customer response ('{engagement.response[:50]}...') remains.")
    except Exception as e:
        db.rollback()
        logger.error(f"DELETE /engagement-workflow/{engagement_id}: Database error during commit: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update engagement in database.")
    
    return {
        "message": "AI draft cleared successfully.",
        "engagement": { 
            "id": engagement.id,
            "customer_id": engagement.customer_id,
            "response": engagement.response,
            "ai_response": engagement.ai_response, # This will now be null
            "status": engagement.status,
            # Include other fields from your Engagement model/schema if needed by frontend
            "sent_at": engagement.sent_at.isoformat() if engagement.sent_at else None,
            "created_at": engagement.created_at.isoformat() if engagement.created_at else None,
            "message_id": engagement.message_id
        }
    }

class EngagementStatusUpdatePayload(BaseModel): # Pydantic model for request body
    status: str

@router.put("/{engagement_id}/status", summary="Update the status of an engagement")
def update_engagement_status(
    engagement_id: int,
    payload: EngagementStatusUpdatePayload, # Use a Pydantic model for the payload
    db: Session = Depends(get_db)
):
    """
    Updates the status of a specific engagement.
    For example, can be used to mark an engagement as 'dismissed' or 'actioned'.
    """
    engagement = db.query(Engagement).filter(Engagement.id == engagement_id).first()

    if not engagement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    new_status = payload.status.strip().lower()
    
    # Optional: Validate the new_status against a list of allowed statuses
    allowed_statuses_for_manual_update = ["dismissed", "actioned", "closed", "pending_review"] # Add more as needed
    if new_status not in allowed_statuses_for_manual_update:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status value. Allowed values are: {', '.join(allowed_statuses_for_manual_update)}"
        )

    logger.info(f"Updating status of engagement ID {engagement_id} from '{engagement.status}' to '{new_status}'.")
    engagement.status = new_status
    engagement.updated_at = datetime.utcnow() # Update the timestamp


    try:
        db.commit()
        db.refresh(engagement)
        return {
            "message": f"Engagement status updated to '{new_status}' successfully.",
            "engagement_id": engagement.id,
            "new_status": engagement.status
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Database error updating engagement status for ID {engagement_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update engagement status.")