# backend/app/routes/conversation_routes.py

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from datetime import datetime # Removed unused `timezone` alias from here
import pytz # Keep pytz for timezone operations
from pydantic import BaseModel # Keep if ManualReplyInput or other local models use it
from app.database import get_db
from app.models import Engagement, Customer, Message, BusinessProfile, Conversation as ConversationModel
from app.celery_tasks import process_scheduled_message_task # Keep if send_manual_reply uses it
import uuid
# Schemas are used for response models and request bodies if defined in app.schemas
from app.schemas import Conversation, ConversationCreate, ConversationUpdate # Ensure these are correct
from typing import List

import logging
logger = logging.getLogger(__name__)

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
    # Eager load conversations and their last message/engagement to optimize
    # This is a conceptual optimization; exact query might need refinement based on your models
    customers = db.query(Customer).filter(Customer.business_id == business.id).options(
        joinedload(Customer.conversations).joinedload(ConversationModel.messages), # Example
        joinedload(Customer.engagements) # Example
    ).all()
    result = []
    logger.info(f"get_open_conversations: Found {len(customers)} customers for business_id={business.id}")

    for customer in customers:
        # This logic for last_engagement can be complex and slow if done per customer.
        # Consider optimizing if performance becomes an issue, e.g., a more complex SQL query.
        last_engagement = (
            db.query(Engagement)
            .filter(Engagement.customer_id == customer.id, Engagement.business_id == business.id) # Ensure correct business
            .order_by(Engagement.created_at.desc())
            .first()
        )
        
        # Also consider the last 'Message' record if engagements aren't the only source of interaction
        last_message_record = (
            db.query(Message)
            .filter(Message.customer_id == customer.id, Message.business_id == business.id)
            .order_by(Message.created_at.desc())
            .first()
        )

        last_interaction_timestamp = None
        interaction_status = "no_recent_interaction"
        last_message_text = "No recent messages."
        conversation_id_for_link = None

        # Determine the most recent interaction between Engagement and Message
        last_eng_time = last_engagement.created_at if last_engagement else datetime.min.replace(tzinfo=pytz.UTC)
        last_msg_time = last_message_record.created_at if last_message_record else datetime.min.replace(tzinfo=pytz.UTC)

        if last_engagement and last_eng_time >= last_msg_time:
            timestamp = last_engagement.created_at 
            conversation_query = db.query(ConversationModel.id).filter(
                ConversationModel.customer_id == customer.id,
                ConversationModel.business_id == business.id
            ).first()
            if conversation_query:
                conversation_id_for_link = str(conversation_query[0])


            if last_engagement.response: # Customer's message was last via engagement
                interaction_status = "pending_review" # Or "customer_replied"
                last_message_text = last_engagement.response
            elif last_engagement.ai_response: # Business's message was last via engagement
                interaction_status = last_engagement.status 
                last_message_text = last_engagement.ai_response
                timestamp = last_engagement.sent_at or last_engagement.created_at
            last_interaction_timestamp = timestamp
        elif last_message_record: # Message record is more recent or only one existing
            # This part needs refinement based on how you want to show 'Message' table entries in inbox summary
            last_message_text = last_message_record.content
            interaction_status = last_message_record.status
            last_interaction_timestamp = last_message_record.sent_at or last_message_record.scheduled_time or last_message_record.created_at
            if last_message_record.conversation_id:
                conversation_id_for_link = str(last_message_record.conversation_id)


        if last_interaction_timestamp: # Only add if there was some interaction
            result.append({
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "last_message": last_message_text,
                "status": interaction_status,
                "timestamp": last_interaction_timestamp.isoformat() if last_interaction_timestamp else None,
                "conversation_id": conversation_id_for_link # Add conversation_id here
            })
        else:
             logger.debug(f"get_open_conversations: No relevant interactions found for customer_id={customer.id}")

    result.sort(key=lambda x: x["timestamp"] or datetime.min.replace(tzinfo=pytz.UTC).isoformat(), reverse=True)
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
    if not business: # Should not happen if customer has business_id, but good check
        logger.error(f"get_conversation_history: Business not found for customer {customer_id} (business_id: {customer.business_id}).")
        raise HTTPException(status_code=500, detail="Business data not found for customer.")

    business_tz_str = business.timezone if business else "UTC"
    try:
        business_tz = pytz.timezone(business_tz_str)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning(f"get_conversation_history: Invalid business timezone '{business_tz_str}' for business {business.id}, using UTC.")
        business_tz = pytz.UTC

    # Fetch messages and engagements, ensuring they belong to the correct business
    messages_query = db.query(Message).filter(
        Message.customer_id == customer_id, Message.business_id == business.id
    ).order_by(Message.created_at.asc())
    
    engagements_query = db.query(Engagement).filter(
        Engagement.customer_id == customer_id, Engagement.business_id == business.id
    ).order_by(Engagement.created_at.asc())

    all_messages_from_db = messages_query.all()
    all_engagements_from_db = engagements_query.all()
    logger.info(f"get_conversation_history: Found {len(all_messages_from_db)} Message records and {len(all_engagements_from_db)} Engagement records for customer_id={customer_id}, business_id={business.id}")

    combined_history = []
    # Use a set to track Message record IDs that have been processed via their Engagement link
    # to avoid duplicating messages that might exist in both tables conceptually
    # (e.g., an AI reply is in Engagement.ai_response and also has a corresponding Message record after being sent)
    processed_message_ids_via_engagement = set()

    # Process Engagements first
    for eng_record in all_engagements_from_db:
        # Determine the primary timestamp for the engagement event for display and sorting
        # Prefer sent_at for sent messages, otherwise created_at
        event_time_utc = eng_record.sent_at if eng_record.sent_at and eng_record.status in ["sent", "auto_replied_faq", "delivered"] else eng_record.created_at
        timestamp_local_str = event_time_utc.astimezone(business_tz).isoformat() if event_time_utc else None
        
        # Handle customer's inbound message part of the engagement
        if eng_record.response:
            combined_history.append({
                "id": f"eng-cust-{eng_record.id}", # Unique ID for this part of engagement
                "type": "customer",
                "text": eng_record.response,
                "timestamp": eng_record.created_at.astimezone(business_tz).isoformat() if eng_record.created_at else None,
                "status": "received", # Customer messages are 'received'
                "source": "customer_reply",
                "sort_time": eng_record.created_at # Use created_at for sorting customer replies
            })

        # Handle AI/business response part of the engagement
        if eng_record.ai_response:
            msg_type = "unknown_business_message" # Default
            source_type = "engagement_related"    # Default

            if eng_record.status == "auto_replied_faq":
                msg_type = "sent" # Autopilot FAQ replies are "sent" by the business
                source_type = "autopilot_faq_reply"
            elif eng_record.status == "sent": # Manually sent replies from review queue, or other direct sends via engagement
                msg_type = "sent"
                source_type = "manual_engagement_reply" # More specific
            elif eng_record.status in ["pending_review", "dismissed"]:
                msg_type = "ai_draft" # This is a draft
                source_type = "ai_draft_suggestion"
            elif eng_record.status in ["failed", "failed_to_send"]:
                msg_type = "failed_to_send" # Or just "failed"
                source_type = "engagement_send_failure"
            # Add other specific engagement statuses if needed (e.g., "delivered", "read" by customer if tracked)

            combined_history.append({
                "id": f"eng-ai-{eng_record.id}", # Unique ID for this part of engagement
                "type": msg_type,
                "text": eng_record.ai_response,
                "timestamp": timestamp_local_str, # Uses event_time_utc localized
                "status": eng_record.status,      # Raw engagement status
                "source": source_type,
                "sort_time": event_time_utc
            })
            
            if eng_record.message_id: # If this engagement is linked to a Message table record
                processed_message_ids_via_engagement.add(eng_record.message_id)

    # Process records from Message table (typically scheduled, non-engagement-driven messages)
    for msg_record in all_messages_from_db:
        if msg_record.id in processed_message_ids_via_engagement:
            logger.debug(f"get_conversation_history: Message ID {msg_record.id} already processed via linked engagement. Skipping.")
            continue
        if msg_record.is_hidden: # Skip hidden messages
            continue

        # Determine the primary timestamp for the message event
        event_time_utc = msg_record.sent_at or msg_record.scheduled_time or msg_record.created_at
        timestamp_local_str = event_time_utc.astimezone(business_tz).isoformat() if event_time_utc else None

        source_type = "unknown_source"
        if msg_record.message_metadata and isinstance(msg_record.message_metadata, dict):
            source_type = msg_record.message_metadata.get('source', 'message_table_entry')
        elif msg_record.message_type == 'scheduled': # Fallback for older scheduled messages
            source_type = 'scheduled_broadcast' # Or a more generic term

        msg_display_type = "unknown"
        if msg_record.message_type == 'inbound': # Customer message logged directly to Message table
            msg_display_type = "customer"
        elif msg_record.message_type == 'outbound' or msg_record.message_type == 'scheduled':
            if msg_record.status == "sent":
                msg_display_type = "sent"
            elif msg_record.status == "scheduled":
                msg_display_type = "scheduled_pending" # For UI to show it's upcoming
            elif msg_record.status == "failed":
                msg_display_type = "failed_to_send"
            # Add other Message statuses as needed
        
        combined_history.append({
            "id": f"msg-{msg_record.id}", # Unique ID for this message
            "type": msg_display_type,
            "text": msg_record.content,
            "timestamp": timestamp_local_str,
            "status": msg_record.status, # Raw status from Message table
            "source": source_type,
            "sort_time": event_time_utc
        })

    # Sort the combined history by the UTC sort_time
    combined_history.sort(key=lambda x: x.get("sort_time") or datetime.min.replace(tzinfo=pytz.UTC))

    # Clean up the sort_time key from the final response objects
    for item in combined_history:
        if "sort_time" in item:
            del item["sort_time"]

    logger.info(f"get_conversation_history: Returning {len(combined_history)} history items for customer_id={customer_id}")
    return {
        "customer": {
            "id": customer.id,
            "name": customer.customer_name,
            "phone": customer.phone
            # You can add more customer details here if needed by the frontend
            # "opted_in": customer.opted_in,
            # "lifecycle_stage": customer.lifecycle_stage,
        },
        "messages": combined_history
    }


# -------------------------------
# POST a manual reply from the business owner (FROM INBOX)
# -------------------------------
class ManualReplyInput(BaseModel): # Keep this Pydantic model for request body validation
    message: str

@router.post("/customer/{customer_id}/reply")
def send_manual_reply(customer_id: int, payload: ManualReplyInput, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        logger.error(f"send_manual_reply: Customer {customer_id} not found.")
        raise HTTPException(status_code=404, detail="Customer not found")

    if not customer.business_id: # Should always have one from creation logic
        logger.error(f"send_manual_reply: Customer {customer_id} does not have a business_id.")
        raise HTTPException(status_code=500, detail="Customer is not associated with a business.")

    logger.info(f"send_manual_reply: Initiated for customer_id={customer_id}, business_id={customer.business_id}")

    now_utc = datetime.now(pytz.UTC)

    # Find or create an active conversation
    conversation = db.query(ConversationModel).filter(
        ConversationModel.customer_id == customer.id,
        ConversationModel.business_id == customer.business_id, # Important: ensure conversation is for this business
        ConversationModel.status == 'active'
    ).first()

    if not conversation:
        logger.info(f"send_manual_reply: No active conversation found for customer_id={customer_id}, business_id={customer.business_id}. Creating new one.")
        conversation = ConversationModel(
            id=uuid.uuid4(), # Generate a new UUID
            customer_id=customer.id,
            business_id=customer.business_id,
            started_at=now_utc,
            last_message_at=now_utc, # Set initial last message time
            status='active'
        )
        db.add(conversation)
        try:
             db.flush() # Assigns ID to conversation
             logger.info(f"send_manual_reply: Created new conversation_id={conversation.id}")
        except Exception as e:
             db.rollback()
             logger.error(f"send_manual_reply: Error flushing new conversation: {str(e)}", exc_info=True)
             raise HTTPException(status_code=500, detail="Failed to initialize conversation.")
    else:
        conversation.last_message_at = now_utc # Update last message time on existing conversation


    # Create a Message record for this manual reply
    # This message will be picked up by Celery to be sent
    message_record = Message(
        conversation_id=conversation.id,
        customer_id=customer.id,
        business_id=customer.business_id,
        content=payload.message,
        message_type='scheduled', # Treat as scheduled for Celery to pick up
        status="scheduled",       # Initial status for Celery
        scheduled_time=now_utc,   # Schedule for immediate processing
        message_metadata={
            'source': 'manual_reply_inbox' # Specific source
        }
    )
    db.add(message_record)
    try:
        db.flush() # Assigns ID to message_record
        logger.info(f"send_manual_reply: Created Message record_id={message_record.id} to be sent by Celery.")
    except Exception as e:
         db.rollback()
         logger.error(f"send_manual_reply: Error flushing new message record: {str(e)}", exc_info=True)
         raise HTTPException(status_code=500, detail="Failed to create message record for sending.")

    # Create an Engagement record to log this manual outbound message
    # The status will be updated by the Celery task once sent/failed
    new_engagement = Engagement(
        customer_id=customer.id,
        message_id=message_record.id, # Link to the Message record created above
        response=None, # No customer response for this specific engagement event
        ai_response=payload.message, # The content of the manual reply
        status="processing_send",  # Indicates it's handed off to Celery; will become 'sent' or 'failed'
        sent_at=None, # Celery task will set this
        business_id=customer.business_id,
        created_at=now_utc # Engagement creation time
    )
    db.add(new_engagement)
    logger.info(f"send_manual_reply: Created Engagement record (ID pending) with status='processing_send' linked to message_id={message_record.id}")

    try:
        db.commit()
        db.refresh(new_engagement) # Get the ID of the new_engagement
        logger.info(f"send_manual_reply: Database commit successful. Message_id={message_record.id}, New Engagement_id={new_engagement.id}")
    except Exception as e:
        db.rollback()
        logger.error(f"send_manual_reply: Database commit error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save reply to database.")

    # Trigger Celery task to send the message
    try:
        task_result = process_scheduled_message_task.apply_async(args=[message_record.id]) # No ETA, send ASAP
        logger.info(f"send_manual_reply: Celery task process_scheduled_message_task enqueued for message_id={message_record.id}. Task ID: {task_result.id}")
    except Exception as e:
        logger.error(f"send_manual_reply: Failed to enqueue Celery task for message_id={message_record.id}: {str(e)}", exc_info=True)
        # Log the error, but don't raise an exception here as the DB commit was successful.
        # The message is in DB as "scheduled"; a retry mechanism for Celery or a cleanup task might be needed for robust handling.
        # For now, the client gets success, but admin should monitor Celery.

    return {
        "status": "success", 
        "message": "Reply submitted for sending.", # Informative message for UI
        "message_id": message_record.id, # ID of the Message table record
        "engagement_id": new_engagement.id, # ID of the Engagement table record
        "engagement_status": new_engagement.status # Initial status of the engagement
    }

# --- Standard CRUD for Conversation Model (Optional - Keep commented if not needed now) ---
# @router.post("/", response_model=Conversation) ...
# @router.get("/", response_model=List[Conversation]) ...
# @router.get("/{conversation_id}", response_model=Conversation) ...
# @router.put("/{conversation_id}", response_model=Conversation) ...
# @router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT) ...