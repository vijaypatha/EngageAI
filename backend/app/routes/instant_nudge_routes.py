# backend/app/routes/instant_nudge_routes.py

# Routes for generating and sending Instant Nudges – AI-personalized SMS messages
# Supports drafting based on topic and multi-customer delivery (immediate or scheduled)
# Includes filtering customers based on tags.

# --- Standard Imports ---
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

# --- FastAPI and Pydantic Imports ---
from fastapi import APIRouter, HTTPException, Depends, status # Added status
from pydantic import BaseModel, Field # Added Field

# --- SQLAlchemy Imports ---
from sqlalchemy.orm import Session
from sqlalchemy import func # Keep func import

# --- App Specific Imports ---
from app.database import get_db
# Import necessary models (add Customer, Tag if not present)
from app.models import BusinessProfile, Message, Conversation, Customer as CustomerModel, Tag
# Import services
from app.services.instant_nudge_service import generate_instant_nudge, handle_instant_nudge_batch

logger = logging.getLogger(__name__)

router = APIRouter(
    # No prefix here, will be defined in main.py
    tags=["instant-nudge"] # Keep existing tag
)

# === Schema Definitions (Moved/Modified for Tag Filtering) ===

# --- MODIFIED: Input model for generating message / identifying targets ---
class InstantNudgeTargetingRequest(BaseModel):
    """Defines how to target customers for an instant nudge."""
    topic: str = Field(..., description="The topic/subject for the AI message generation.")
    business_id: int = Field(..., description="The ID of the business sending the nudge.")
    # Allow EITHER specific customer IDs OR tag filters, not both required. Add validation?
    customer_ids: Optional[List[int]] = Field(None, description="Optional: Specific list of customer IDs to target.")
    filter_tags: Optional[List[str]] = Field(None, description="Optional: List of tag names (lowercase) to filter customers by (matches ALL tags).")
    # Add fields needed for scheduling if extending functionality later
    # send_datetime_utc: Optional[str] = None

# --- Existing: Payload model for sending a pre-drafted batch ---
# This model might need adjustment depending on how you handle the flow (generate then send vs. generate-and-send)
# Assuming for now that the sending logic receives customer IDs determined by the targeting request.
class InstantNudgeSendPayload(BaseModel):
    """Payload for the actual sending/scheduling of nudges to specific customers."""
    customer_ids: List[int] = Field(..., description="The final list of customer IDs to send the message to.")
    message: str = Field(..., description="The message content (potentially personalized).")
    business_id: int # Needed for logging/context during sending
    send_datetime_utc: Optional[str] = Field(None, description="Optional: ISO 8601 UTC datetime string for scheduling.")


# === Route Definitions ===

# --- MODIFIED: Endpoint to generate message AND identify targets ---
# This endpoint now handles finding the customer IDs based on criteria.
# It could return the draft + target IDs, or directly trigger the send.
# Let's make it return the draft + IDs for flexibility.
@router.post("/generate-targeted-draft", response_model=Dict[str, Any])
async def generate_targeted_nudge_draft(
    payload: InstantNudgeTargetingRequest,
    db: Session = Depends(get_db)
):
    """
    Generates an AI message draft based on topic and identifies target customer IDs
    based on either specific IDs or tag filters.
    """
    logger.info(f"✍️ Received Instant Nudge generation/targeting request for business_id={payload.business_id} | topic='{payload.topic}' | tags='{payload.filter_tags}' | specific_ids='{payload.customer_ids}'")

    target_customer_ids = set() # Use a set to store unique IDs

    # --- Determine Target Customers ---
    if payload.customer_ids and payload.filter_tags:
        # If both are provided, it's ambiguous - raise an error or prioritize one? Let's raise error.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either 'customer_ids' or 'filter_tags', not both."
        )

    if payload.customer_ids:
        # Use specific customer IDs provided
        target_customer_ids = set(payload.customer_ids)
        # Optional: Validate these customers belong to the business_id
        valid_customers_q = db.query(CustomerModel.id).filter(
            CustomerModel.business_id == payload.business_id,
            CustomerModel.id.in_(target_customer_ids)
        )
        valid_customer_ids = {res[0] for res in valid_customers_q.all()}
        if len(valid_customer_ids) != len(target_customer_ids):
            invalid_ids = target_customer_ids - valid_customer_ids
            logger.warning(f"Provided customer IDs not found or not linked to business {payload.business_id}: {invalid_ids}")
            # Decide: Raise error or proceed with only valid IDs? Let's proceed with valid ones.
            target_customer_ids = valid_customer_ids
        logging.info(f"Targeting specific customer IDs (validated): {target_customer_ids}")

    elif payload.filter_tags:
        # Filter customers by tags if provided
        tag_names = [tag.strip().lower() for tag in payload.filter_tags if tag.strip()]
        if tag_names:
            logging.info(f"Filtering customers for business {payload.business_id} by tags: {tag_names}")
            # Query customers matching ALL tags for this business
            query = db.query(CustomerModel.id).join(CustomerModel.tags).filter(
                CustomerModel.business_id == payload.business_id,
                Tag.name.in_(tag_names)
            ).group_by(CustomerModel.id).having(func.count(Tag.id) == len(tag_names))

            customer_ids_from_tags = {result[0] for result in query.all()}
            target_customer_ids = customer_ids_from_tags
            logging.info(f"Found {len(target_customer_ids)} customers matching tags: {target_customer_ids}")
        else:
            logging.warning("filter_tags provided but resulted in empty list after cleaning.")
            # If tags were provided but empty, maybe return no customers?
            target_customer_ids = set() # Ensure it's empty

    else:
        # Neither specific IDs nor tags provided - this is an invalid request state.
        logging.error("Targeting request must include either 'customer_ids' or 'filter_tags'.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request must include customer_ids or filter_tags to identify targets."
            )

    if not target_customer_ids:
        logging.warning("No target customers identified for the nudge.")
        # Return indicating no targets found
        return {
            "message_draft": None,
            "target_customer_count": 0,
            "target_customer_ids": [],
            "status": "No customers found matching criteria."
            }

    # --- Generate AI Message Draft ---
    try:
        generated_data = await generate_instant_nudge(payload.topic, payload.business_id, db)
        message_draft = generated_data.get("message")
        logger.info(f"Generated nudge draft for topic '{payload.topic}'.")
        if not message_draft:
             logger.error("AI service returned empty message draft.")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate message draft content.")

        # Return the draft and the list of identified customer IDs
        return {
            "message_draft": message_draft,
            "target_customer_count": len(target_customer_ids),
            "target_customer_ids": sorted(list(target_customer_ids)) # Return sorted list
            }

    except Exception as e:
        # Catch errors specifically from the generate_instant_nudge service
        logger.error(f"❌ Instant Nudge generation failed: {e}", exc_info=True)
        # Check if it's an HTTPException already (e.g., business not found)
        if isinstance(e, HTTPException):
             raise e
        raise HTTPException(status_code=500, detail=f"Failed to generate instant nudge message: {e}")


# --- MODIFIED: Endpoint to send/schedule the batch ---
# This endpoint now takes the final list of customers and the message.
# It calls the service function responsible for DB interaction and Celery tasks.
@router.post("/send-batch", status_code=status.HTTP_202_ACCEPTED) # Use 202 Accepted for async tasks
async def send_instant_nudge_batch_final(
    payload: InstantNudgeSendPayload, # Use the new payload schema
    db: Session = Depends(get_db) # Inject DB if handle_instant_nudge_batch needs it (it likely does)
    ):
    """
    Sends or schedules a pre-drafted message to a specific list of customer IDs.
    """
    logging.info(f"📨 Received Instant Nudge batch send request for {len(payload.customer_ids)} customers. Business ID: {payload.business_id}")

    if not payload.customer_ids:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="customer_ids list cannot be empty.")
    if not payload.message:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message content cannot be empty.")

    try:
        # The service function handles creating Message records and scheduling Celery tasks
        # Pass the necessary data from the payload
        result = await handle_instant_nudge_batch(
             db=db, # Pass db session to the service function
             business_id=payload.business_id,
             customer_ids=payload.customer_ids,
             message_content=payload.message,
             send_datetime_iso=payload.send_datetime_utc # Pass optional schedule time
             )

        logger.info(f"✅ Batch processing initiated. Result: {result}")
        # Return result from the service (e.g., list of created message IDs or success status)
        # Using 202 Accepted indicates the task is queued, not necessarily completed.
        return {"status": "accepted", "details": result}

    except ValueError as ve:
         # Catch specific validation errors from the service layer
         logger.error(f"❌ Value error sending instant nudges: {ve}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"❌ Failed to send/schedule instant nudges: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process nudge batch: {e}")


# === Keep Existing Read/Analytics Endpoints (ensure models/fields are correct) ===

# Endpoint to get the status of instant nudges by slug
@router.get("/instant-status/slug/{slug}")
def get_instant_nudge_status(slug: str, db: Session = Depends(get_db)):
    # ... (implementation likely remains the same, ensure Message model fields are correct) ...
    business = db.query(BusinessProfile).filter(BusinessProfile.slug == slug).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    messages = db.query(Message).filter(
        Message.business_id == business.id,
        Message.message_type == 'scheduled',
        # Ensure JSON query syntax is correct for your SQLAlchemy/DB version
        Message.message_metadata.op('->>')('source') == 'instant_nudge'
    ).all()
    # Format response... (ensure fields exist)
    return [
        {
            "id": m.id, "message": m.content, "customer_id": m.customer_id,
            "status": m.status, "send_time": m.scheduled_time, "is_hidden": m.is_hidden,
            "conversation_id": m.conversation_id, "metadata": m.message_metadata
        } for m in messages
    ]


# Endpoint to get detailed instant nudge analytics
@router.get("/nudge/instant-analytics/business/{business_id}")
def get_instant_nudge_analytics(business_id: int, db: Session = Depends(get_db)):
    # ... (implementation likely remains the same, ensure Message model fields are correct) ...
    now_utc = datetime.now(timezone.utc)
    messages = db.query(Message).filter(
        Message.business_id == business_id,
        Message.message_type == 'scheduled',
        Message.message_metadata.op('->>')('source') == 'instant_nudge'
    ).all()
    # Calculate analytics...
    total_sent = sum(1 for m in messages if m.status == 'sent')
    total_scheduled = sum(1 for m in messages if m.status == 'scheduled' and m.scheduled_time and m.scheduled_time > now_utc)
    # Add other statuses if needed (e.g., failed, pending)
    total_failed = sum(1 for m in messages if m.status == 'failed') # Example

    return {
        "total_messages": len(messages), "sent": total_sent,
        "scheduled": total_scheduled, "failed": total_failed,
        # Adjust success rate calculation as needed
        "success_rate": (total_sent / (total_sent + total_failed)) if (total_sent + total_failed) > 0 else 0
    }


# Endpoint to get all instant nudge messages for a customer
@router.get("/nudge/instant-multi/customer/{customer_id}")
def get_instant_nudges_for_customer(customer_id: int, db: Session = Depends(get_db)):
     # ... (implementation likely remains the same, ensure Message model fields are correct) ...
     messages = db.query(Message).filter(
        Message.customer_id == customer_id,
        Message.message_metadata.op('->>')('source') == 'instant_nudge'
     ).order_by(Message.scheduled_time.desc()).all()
     # Format response...
     return [
        {
            "id": m.id, "message": m.content, "customer_id": m.customer_id,
            "status": m.status, "send_time": m.scheduled_time, "is_hidden": m.is_hidden,
            "conversation_id": m.conversation_id, "metadata": m.message_metadata
        } for m in messages
    ]