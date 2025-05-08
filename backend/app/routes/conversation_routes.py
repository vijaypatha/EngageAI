# backend/app/routes/conversation_routes.py

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
from pydantic import BaseModel
from app.database import get_db
from app.models import Engagement, Customer, Message, BusinessProfile, Conversation as ConversationModel
from app.celery_tasks import process_scheduled_message_task
import uuid
import pytz
from app.schemas import Conversation, ConversationCreate, ConversationUpdate # Assuming these are defined
from typing import List
# from ..auth import get_current_user # Keep commented unless needed

# --- Add logging ---
import logging
logger = logging.getLogger(__name__)
# --- End logging ---

router = APIRouter(tags=["Conversations"])

# -------------------------------
# GET inbox summary: all customers with conversations
# -------------------------------
@router.get("/inbox")
def get_open_conversations(business_name: str = Query(...), db: Session = Depends(get_db)):
    logger.info(f"get_open_conversations: Fetching inbox for business_name='{business_name}'")
    business = db.query(BusinessProfile).filter(BusinessProfile.business_name == business_name).first()
    if not business:
        logger.warning(f"get_open_conversations: Business not found for name='{business_name}'")
        raise HTTPException(status_code=404, detail="Business not found")

    logger.info(f"get_open_conversations: Found business_id={business.id}")
    customers = db.query(Customer).filter(Customer.business_id == business.id).all()
    result = []
    logger.info(f"get_open_conversations: Found {len(customers)} customers for business_id={business.id}")

    for customer in customers:
        last_engagement = (
            db.query(Engagement)
            .filter(Engagement.customer_id == customer.id)
            .order_by(Engagement.created_at.desc()) # Order by creation time
            .first()
        )
        if last_engagement:
            interaction_status = "unknown"
            last_message_text = ""
            timestamp = last_engagement.created_at # Default timestamp

            if last_engagement.response: # Customer's message was last
                interaction_status = "pending_review"
                last_message_text = last_engagement.response
            elif last_engagement.ai_response: # Business's message was last
                interaction_status = last_engagement.status # Reflect the status of the outgoing message
                last_message_text = last_engagement.ai_response
                timestamp = last_engagement.sent_at or last_engagement.created_at # Use sent_at if available

            result.append({
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "last_message": last_message_text,
                "status": interaction_status,
                "timestamp": timestamp.isoformat() if timestamp else None,
            })
        else:
             logger.debug(f"get_open_conversations: No engagements found for customer_id={customer.id}")

    result.sort(key=lambda x: x["timestamp"] or datetime.min.isoformat(), reverse=True)
    logger.info(f"get_open_conversations: Returning {len(result)} conversations for business_id={business.id}")
    return {"conversations": result}

# -------------------------------
# GET full chat history for a specific customer
# -------------------------------
@router.get("/customer/{customer_id}")
def get_conversation_history(customer_id: int, db: Session = Depends(get_db)):
    logger.info(f"get_conversation_history: Fetching history for customer_id={customer_id}")
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        logger.warning(f"get_conversation_history: Customer {customer_id} not found.")
        raise HTTPException(status_code=404, detail="Customer not found")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
    business_tz_str = business.timezone if business else "UTC"
    try:
        business_tz = pytz.timezone(business_tz_str)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning(f"get_conversation_history: Invalid business timezone '{business_tz_str}', using UTC.")
        business_tz = pytz.UTC

    messages_query = db.query(Message).filter(Message.customer_id == customer_id).order_by(Message.created_at.asc())
    engagements_query = db.query(Engagement).filter(Engagement.customer_id == customer_id).order_by(Engagement.created_at.asc())

    all_messages = messages_query.all()
    all_engagements = engagements_query.all()
    logger.info(f"get_conversation_history: Found {len(all_messages)} message records and {len(all_engagements)} engagement records for customer_id={customer_id}")

    combined_history = []
    processed_message_ids = set()

    for eng in all_engagements:
        # Display time is engagement creation time unless it's a sent message with a sent_at time
        display_time = eng.sent_at if eng.sent_at and eng.status == "sent" else eng.created_at
        timestamp_local = display_time.astimezone(business_tz) if display_time else None
        sort_time = display_time # Keep UTC for sorting

        if eng.response: # Customer's inbound message
            combined_history.append({
                "id": f"eng-cust-{eng.id}",
                "type": "customer",
                "text": eng.response,
                "timestamp": timestamp_local, # Use localized timestamp
                "status": "received",
                "source": "customer_reply",
                "sort_time": eng.created_at # Sort customer replies by creation time
            })

        if eng.ai_response: # Business's outbound message recorded in engagement
            if eng.message_id:
                 processed_message_ids.add(eng.message_id)

            # Determine type based on status stored in DB (will be 'sent' due to revert)
            msg_type = "ai_draft" if eng.status not in ["sent", "delivered", "failed", "processing"] else "sent"

            combined_history.append({
                "id": f"eng-ai-{eng.id}",
                "type": msg_type, # UI should now interpret as 'sent'
                "text": eng.ai_response,
                "timestamp": timestamp_local, # Use localized timestamp
                "status": eng.status,
                "source": "engagement_reply",
                "sort_time": sort_time # Sort outgoing by sent_at or created_at
            })

    for msg in all_messages:
        if msg.id in processed_message_ids:
            logger.debug(f"get_conversation_history: Skipping message_id={msg.id} as handled by engagement.")
            continue
        if msg.is_hidden:
             continue

        effective_timestamp = msg.sent_at or msg.scheduled_time or msg.created_at
        timestamp_local = effective_timestamp.astimezone(business_tz) if effective_timestamp else None
        sort_time = effective_timestamp # UTC for sorting

        source = 'unknown'
        if msg.message_metadata and isinstance(msg.message_metadata, dict):
             source = msg.message_metadata.get('source', 'unknown')
        elif msg.message_type == 'scheduled':
             source = 'scheduled'

        # Determine type based on status
        msg_type = "sent" if msg.status == "sent" else "scheduled" # Or map other statuses

        combined_history.append({
            "id": f"msg-{msg.id}",
            "type": msg_type,
            "text": msg.content,
            "timestamp": timestamp_local,
            "status": msg.status,
            "source": source,
            "sort_time": sort_time
        })

    combined_history.sort(key=lambda x: x.get("sort_time") or datetime.min.replace(tzinfo=pytz.UTC))

    for item in combined_history:
        if item.get("timestamp"):
            item["timestamp"] = item["timestamp"].isoformat()
        if "sort_time" in item:
             del item["sort_time"]

    logger.info(f"get_conversation_history: Returning {len(combined_history)} history items for customer_id={customer_id}")
    return {
        "customer": {
            "id": customer.id,
            "name": customer.customer_name,
            "phone": customer.phone
        },
        "messages": combined_history
    }

# -------------------------------
# POST a manual reply from the business owner (FROM INBOX) - STATUS REVERTED
# -------------------------------
class ManualReplyInput(BaseModel):
    message: str

@router.post("/customer/{customer_id}/reply")
def send_manual_reply(customer_id: int, payload: ManualReplyInput, db: Session = Depends(get_db)):
    # --- STATUS REVERTED TO 'sent' ---
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        logger.error(f"send_manual_reply: Customer {customer_id} not found.")
        raise HTTPException(status_code=404, detail="Customer not found")

    if not customer.business_id:
        logger.error(f"send_manual_reply: Customer {customer_id} does not have a business_id.")
        raise HTTPException(status_code=500, detail="Customer is not associated with a business.")

    logger.info(f"send_manual_reply: Initiated for customer_id={customer_id}, business_id={customer.business_id}")

    now_utc = datetime.now(pytz.UTC)

    conversation = db.query(ConversationModel).filter(
        ConversationModel.customer_id == customer.id,
        ConversationModel.business_id == customer.business_id,
        ConversationModel.status == 'active'
    ).first()

    if not conversation:
        logger.info(f"send_manual_reply: No active conversation found for customer_id={customer_id}. Creating new one.")
        conversation = ConversationModel(
            id=uuid.uuid4(),
            customer_id=customer.id,
            business_id=customer.business_id,
            started_at=now_utc,
            last_message_at=now_utc,
            status='active'
        )
        db.add(conversation)
        try:
             db.flush()
             logger.info(f"send_manual_reply: Created new conversation_id={conversation.id}")
        except Exception as e:
             db.rollback()
             logger.error(f"send_manual_reply: Error flushing new conversation: {str(e)}", exc_info=True)
             raise HTTPException(status_code=500, detail="Failed to initialize conversation.")

    message_record = Message(
        conversation_id=conversation.id,
        customer_id=customer.id,
        business_id=customer.business_id,
        content=payload.message,
        message_type='scheduled',
        status="scheduled",
        scheduled_time=now_utc,
        message_metadata={
            'source': 'manual_reply_inbox'
        }
    )
    db.add(message_record)
    try:
        db.flush()
        logger.info(f"send_manual_reply: Created Message record_id={message_record.id}")
    except Exception as e:
         db.rollback()
         logger.error(f"send_manual_reply: Error flushing new message record: {str(e)}", exc_info=True)
         raise HTTPException(status_code=500, detail="Failed to create message record.")

    new_engagement = Engagement(
        customer_id=customer.id,
        message_id=message_record.id,
        response=None,
        ai_response=payload.message,
        status="sent",  # <<< REVERTED back to "sent"
        sent_at=now_utc, # <<< REVERTED back to setting sent_at immediately
        business_id=customer.business_id # Keep the business_id fix
    )
    db.add(new_engagement)
    logger.info(f"send_manual_reply: Created Engagement record with business_id={new_engagement.business_id}, status='{new_engagement.status}' linked to message_id={message_record.id}")

    try:
        db.commit()
        logger.info(f"send_manual_reply: Database commit successful for message_id={message_record.id} and new engagement_id={new_engagement.id}")
    except Exception as e:
        db.rollback()
        logger.error(f"send_manual_reply: Database commit error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save reply.")

    try:
        task_result = process_scheduled_message_task.apply_async(args=[message_record.id])
        logger.info(f"send_manual_reply: Celery task process_scheduled_message_task enqueued for message_id={message_record.id}. Task ID: {task_result.id}")
    except Exception as e:
        logger.error(f"send_manual_reply: Failed to enqueue Celery task for message_id={message_record.id}: {str(e)}", exc_info=True)
        # Log only, don't raise - DB commit succeeded

    return {
        "status": "success", # Return success for UI
        "message": "Reply submitted for sending.",
        "message_id": message_record.id,
        "engagement_status": new_engagement.status # Reflects 'sent' status
    }

# --- Standard CRUD for Conversation Model (Optional - Keep commented if not needed now) ---
# @router.post("/", response_model=Conversation) ...
# @router.get("/", response_model=List[Conversation]) ...
# @router.get("/{conversation_id}", response_model=Conversation) ...
# @router.put("/{conversation_id}", response_model=Conversation) ...
# @router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT) ...