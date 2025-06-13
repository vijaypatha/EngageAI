# backend/app/routes/conversation_routes.py

from datetime import datetime, timezone as dt_timezone
import logging
import traceback
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Request, status, Response, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, cast, Integer, text # Added cast, Integer, text
import pytz
from typing import Optional, List, Dict, Any
from pydantic import BaseModel  # Added BaseModel import

from app.database import get_db
from app.models import (
    BusinessProfile,
    Engagement,
    Message,
    Conversation as ConversationModel,
    ConsentLog,
    Customer,
    CoPilotNudge, # Imported CoPilotNudge
    NudgeTypeEnum, # Imported NudgeTypeEnum
    NudgeStatusEnum, # Imported NudgeStatusEnum
    MessageTypeEnum,
    MessageStatusEnum
)

from app.services.ai_service import AIService
from app.services.consent_service import ConsentService
from app.config import settings
from app.services.twilio_service import TwilioService

from app.schemas import normalize_phone_number as normalize_phone, MessageCreateSchema, MessageResponse # Added MessageResponse
# from app.models import MessageTypeEnum, MessageStatusEnum # Already imported from app.models, no need to re-import
import re

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Conversations"]) # Added tag consistency


@router.post("/customer/{customer_id}/send-message", response_model=MessageResponse) # Added response_model
async def send_message_from_inbox(
    customer_id: int, # Changed from uuid.UUID to int
    payload: MessageCreateSchema,
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
    if not business:
        # This should ideally not happen if data integrity is maintained
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found for customer")

    conversation = db.query(ConversationModel).filter(
        ConversationModel.customer_id == customer.id,
        ConversationModel.business_id == business.id,
        ConversationModel.status == 'active'
    ).first()

    now_utc = datetime.now(dt_timezone.utc)

    if not conversation:
        conversation = ConversationModel(
            id=uuid.uuid4(),
            customer_id=customer.id,
            business_id=business.id,
            started_at=now_utc,
            last_message_at=now_utc,
            status='active'
        )
        db.add(conversation)
        db.flush()  # Flush to get conversation.id if it's new

    db_message = Message(
        conversation_id=conversation.id,
        business_id=business.id,
        customer_id=customer.id,
        content=payload.message,
        message_type=MessageTypeEnum.OUTBOUND.value,
        status=MessageStatusEnum.QUEUED.value, # Initial status
        created_at=now_utc,
        sent_at=None,
        message_metadata={'source': 'manual_inbox_reply'}
    )
    db.add(db_message)
    db.flush() # Flush to get db_message.id for twilio_service and for metadata updates

    twilio_service = TwilioService(db=db)

    try:
        sent_message_sid = await twilio_service.send_sms(
            to=customer.phone,
            message_body=payload.message,
            business=business,
            customer=customer, # Pass customer object
            is_direct_reply=True # Explicitly state this is a direct reply
        )

        if sent_message_sid:
            db_message.status = MessageStatusEnum.SENT.value
            db_message.sent_at = datetime.now(dt_timezone.utc)
            db_message.message_metadata['twilio_sid'] = sent_message_sid
            logger.info(f"Message SID {sent_message_sid} from Twilio stored for message {db_message.id}")
        else:
            # This case might indicate an issue with how send_sms signals failure,
            # as it's expected to raise HTTPException on failure.
            db_message.status = MessageStatusEnum.FAILED.value
            db_message.message_metadata['error'] = 'Send SMS returned no SID and did not raise error.'
            logger.error(f"Send SMS returned no SID for message {db_message.id}. Payload: {payload.message}")
            # We will commit this FAILED status, but also raise to inform client
            db.commit()
            db.refresh(db_message)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send message via Twilio, no SID received.")

    except HTTPException as e:
        db_message.status = MessageStatusEnum.FAILED.value
        db_message.message_metadata['error'] = str(e.detail)
        db_message.message_metadata['error_code'] = e.status_code
        logger.error(f"HTTPException when sending SMS for message {db_message.id}: {e.detail}")
        db.commit() # Commit the failure status
        db.refresh(db_message)
        raise e # Re-throw the exception to the client
    except Exception as e:
        # Catch any other unexpected errors
        db_message.status = MessageStatusEnum.FAILED.value
        db_message.message_metadata['error'] = f"Unexpected error: {str(e)}"
        logger.error(f"Unexpected error when sending SMS for message {db_message.id}: {str(e)}", exc_info=True)
        db.commit()
        db.refresh(db_message)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

    conversation.last_message_at = db_message.sent_at if db_message.sent_at else now_utc
    db.commit()
    db.refresh(db_message)
    db.refresh(conversation)

    return db_message # Corrected return: return the ORM object which will be serialized by Pydantic's response_model


@router.get("/customer/{customer_id}", response_model=Dict[str, Any]) # Changed response_model to Dict[str, Any] as it returns a dict
def get_conversation_history(customer_id: int, db: Session = Depends(get_db)):
    logger.info(f"get_conversation_history: Fetching history for customer_id={customer_id}")
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        logger.warning(f"get_conversation_history: Customer {customer_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
    if not business: # Should not happen if customer has business_id, but good check
        logger.error(f"get_conversation_history: Business not found for customer {customer_id} (business_id: {customer.business_id}).")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Business data not found for customer.")

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
    processed_message_ids_via_engagement = set()

    # --- Fetch Nudges related to Inbound Messages ---
    # Fetch all relevant nudges once for efficiency
    inbound_message_ids_in_history = [
        msg.id for msg in all_messages_from_db
        if msg.message_type == MessageTypeEnum.INBOUND.value
    ]
    
    related_nudges = {}
    if inbound_message_ids_in_history:
        nudges_orm = db.query(CoPilotNudge).filter(
            CoPilotNudge.business_id == business.id,
            CoPilotNudge.customer_id == customer.id, # Nudges are customer-specific
            CoPilotNudge.nudge_type == NudgeTypeEnum.SENTIMENT_POSITIVE, # Only looking for this type for "Request Review"
            CoPilotNudge.status == NudgeStatusEnum.ACTIVE.value, # Only active nudges are actionable
            CoPilotNudge.ai_evidence_snippet.op('->>')('original_message_id').cast(Integer).in_(inbound_message_ids_in_history)
        ).all()
        for nudge in nudges_orm:
            # The original_message_id is stored as string in JSON, cast it to int for lookup
            original_msg_id = nudge.ai_evidence_snippet.get('original_message_id')
            if original_msg_id is not None:
                try:
                    related_nudges[int(original_msg_id)] = {
                        "nudge_id": nudge.id,
                        "nudge_type": nudge.nudge_type,
                        "nudge_status": nudge.status,
                        "ai_suggestion": nudge.ai_suggestion
                    }
                except ValueError:
                    logger.warning(f"Nudge {nudge.id} has invalid original_message_id: {original_msg_id}")


    # Process Engagements first
    for eng_record in all_engagements_from_db:
        # Determine the primary timestamp for the engagement event for display and sorting
        # Prefer sent_at for sent messages, otherwise created_at
        event_time_utc = eng_record.sent_at if eng_record.sent_at and eng_record.status in [MessageStatusEnum.SENT.value, MessageStatusEnum.AUTO_REPLIED_FAQ.value, MessageStatusEnum.DELIVERED.value] else eng_record.created_at
        timestamp_local_str = event_time_utc.astimezone(business_tz).isoformat() if event_time_utc else None
        
        # Handle customer's inbound message part of the engagement
        if eng_record.response:
            # Check for contextual action if this inbound message (via engagement.message_id) has one
            contextual_action = None
            if eng_record.message_id and eng_record.message_id in related_nudges:
                nudge_data = related_nudges[eng_record.message_id]
                # Assuming 'REQUEST_REVIEW' is the action type for SENTIMENT_POSITIVE nudges
                if nudge_data['nudge_type'] == NudgeTypeEnum.SENTIMENT_POSITIVE:
                    contextual_action = {
                        "type": "REQUEST_REVIEW",
                        "nudge_id": nudge_data['nudge_id'],
                        "ai_suggestion": nudge_data['ai_suggestion']
                    }

            combined_history.append({
                "id": f"eng-cust-{eng_record.id}", # Unique ID for this part of engagement
                "type": MessageTypeEnum.INBOUND.value, # Changed from "customer" to "inbound" for consistency with frontend
                "content": eng_record.response, # Changed from "text" to "content"
                "timestamp": eng_record.created_at.astimezone(business_tz).isoformat() if eng_record.created_at else None,
                "status": MessageStatusEnum.RECEIVED.value, # Customer messages are 'received'
                "source": "customer_reply",
                "sort_time": eng_record.created_at, # Use created_at for sorting customer replies
                "contextual_action": contextual_action # Add contextual action if present
            })

        # Handle AI/business response part of the engagement
        if eng_record.ai_response:
            msg_type = "unknown_business_message" # Default
            source_type = "engagement_related"    # Default

            if eng_record.status == MessageStatusEnum.AUTO_REPLIED_FAQ.value:
                msg_type = MessageTypeEnum.OUTBOUND_AI_REPLY.value # Explicitly use Enum value
                source_type = "autopilot_faq_reply"
            elif eng_record.status == MessageStatusEnum.SENT.value: # Manually sent replies from review queue, or other direct sends via engagement
                msg_type = MessageTypeEnum.OUTBOUND.value # Explicitly use Enum value
                source_type = "manual_engagement_reply" # More specific
            elif eng_record.status in [MessageStatusEnum.PENDING_REVIEW.value, NudgeStatusEnum.DISMISSED.value]: # These are AI drafts on frontend
                msg_type = MessageTypeEnum.INBOUND.value # AI drafts are attached to inbound messages on frontend
                source_type = "ai_draft_suggestion"
            elif eng_record.status in [MessageStatusEnum.FAILED.value, MessageStatusEnum.FAILED_TO_SEND.value]: # Or just "failed"
                msg_type = MessageStatusEnum.FAILED_TO_SEND.value # Consistent with frontend `TimelineEntry` type
                source_type = "engagement_send_failure"
            # Add other specific engagement statuses if needed (e.g., "delivered", "read" by customer if tracked)

            # Extract content from ai_response JSON string
            ai_content = ""
            parsed_ai_response_dict: Dict[str, Any] = {}
            try:
                if isinstance(eng_record.ai_response, str):
                    parsed_ai_response_dict = json.loads(eng_record.ai_response)
                    ai_content = parsed_ai_response_dict.get("text", "")
            except (json.JSONDecodeError, AttributeError):
                ai_content = eng_record.ai_response # Fallback if not JSON or parsing fails

            combined_history.append({
                "id": f"eng-ai-{eng_record.id}", # Unique ID for this part of engagement
                "type": msg_type,
                "content": ai_content, # Use "content" to match frontend `TimelineEntry`
                "timestamp": timestamp_local_str, # Uses event_time_utc localized
                "status": eng_record.status,      # Raw engagement status
                "source": source_type,
                "sort_time": event_time_utc,
                "ai_response": ai_content if msg_type == MessageTypeEnum.INBOUND.value else None, # For AI Drafts attached to inbound
                "ai_draft_id": eng_record.id if msg_type == MessageTypeEnum.INBOUND.value else None, # The ID of the engagement for draft actions
                "is_faq_answer": parsed_ai_response_dict.get("is_faq_answer", False) if isinstance(parsed_ai_response_dict, dict) else False,
                "appended_opt_in_prompt": parsed_ai_response_dict.get("appended_opt_in_prompt", False) if isinstance(parsed_ai_response_dict, dict) else False
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
        elif msg_record.message_type == MessageTypeEnum.SCHEDULED.value: # Fallback for older scheduled messages
            source_type = 'scheduled_broadcast' # Or a more generic term

        msg_display_type = "unknown"
        contextual_action = None # Initialize for messages not from engagements
        if msg_record.message_type == MessageTypeEnum.INBOUND.value: # Customer message logged directly to Message table
            msg_display_type = MessageTypeEnum.INBOUND.value
            if msg_record.id in related_nudges: # Check if this inbound message has a related nudge
                nudge_data = related_nudges[msg_record.id]
                if nudge_data['nudge_type'] == NudgeTypeEnum.SENTIMENT_POSITIVE:
                    contextual_action = {
                        "type": "REQUEST_REVIEW",
                        "nudge_id": nudge_data['nudge_id'],
                        "ai_suggestion": nudge_data['ai_suggestion']
                    }
        elif msg_record.message_type == MessageTypeEnum.OUTBOUND.value:
            if msg_record.status == MessageStatusEnum.SENT.value:
                msg_display_type = MessageTypeEnum.OUTBOUND.value
            elif msg_record.status == MessageStatusEnum.SCHEDULED.value:
                msg_display_type = MessageTypeEnum.SCHEDULED.value
            elif msg_record.status == MessageStatusEnum.FAILED.value:
                msg_display_type = MessageStatusEnum.FAILED_TO_SEND.value # Consistent with frontend `TimelineEntry` type
        elif msg_record.message_type == MessageTypeEnum.OUTBOUND_AI_REPLY.value: # Specifically handle AI replies from Message table
            msg_display_type = MessageTypeEnum.OUTBOUND_AI_REPLY.value
        
        # Extract content and metadata for messages
        msg_content = msg_record.content
        is_faq_answer = False
        appended_opt_in_prompt = False

        if isinstance(msg_record.content, str):
            try:
                parsed_content = json.loads(msg_record.content)
                if isinstance(parsed_content, dict) and "text" in parsed_content:
                    msg_content = parsed_content["text"]
                    is_faq_answer = parsed_content.get("is_faq_answer", False)
                    appended_opt_in_prompt = parsed_content.get("appended_opt_in_prompt", False)
            except json.JSONDecodeError:
                pass # Not a JSON string, use as-is

        combined_history.append({
            "id": f"msg-{msg_record.id}", # Unique ID for this message
            "type": msg_display_type,
            "content": msg_content, # Use "content" to match frontend `TimelineEntry`
            "timestamp": timestamp_local_str,
            "status": msg_record.status, # Raw status from Message table
            "source": source_type,
            "sort_time": event_time_utc,
            "is_faq_answer": is_faq_answer,
            "appended_opt_in_prompt": appended_opt_in_prompt,
            "contextual_action": contextual_action # Add contextual action if present
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    if not customer.business_id: # Should always have one from creation logic
        logger.error(f"send_manual_reply: Customer {customer_id} does not have a business_id.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Customer is not associated with a business.")

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
        db.flush() # Assigns ID to conversation
        logger.info(f"send_manual_reply: Created new conversation_id={conversation.id}")
    else:
        conversation.last_message_at = now_utc # Update last message time on existing conversation


    # Create a Message record for this manual reply
    # This message will be picked up by Celery to be sent
    message_record = Message(
        conversation_id=conversation.id,
        customer_id=customer.id,
        business_id=customer.business_id,
        content=payload.message,
        message_type=MessageTypeEnum.SCHEDULED.value, # Treat as scheduled for Celery to pick up
        status=MessageStatusEnum.SCHEDULED.value,      # Initial status for Celery
        scheduled_time=now_utc,    # Schedule for immediate processing
        message_metadata={
            'source': 'manual_reply_inbox' # Specific source
        }
    )
    db.add(message_record)
    db.flush() # Assigns ID to message_record

    # 🔹 Step 7: Schedule with Celery
    task_id_str = None
    try:
        eta_value = message_record.scheduled_time
        if not isinstance(eta_value, datetime):
            eta_value = datetime.fromisoformat(str(eta_value))
        
        if eta_value.tzinfo is None:
            eta_value = pytz.utc.localize(eta_value)
        else:
            eta_value = eta_value.astimezone(pytz.utc)
        
        if eta_value < datetime.now(pytz.utc):
            logger.warning(f"⚠️ ETA for message {message_record.id} is in the past: {eta_value.isoformat()}. Celery may execute immediately.")

        logger.info(f"📤 Attempting to schedule Celery task for Message.id={message_record.id}, ETA (UTC)='{eta_value.isoformat()}'")
        
        from app.celery_tasks import process_scheduled_message_task # Import here to avoid circular dependency
        task_result = process_scheduled_message_task.apply_async(
            args=[message_record.id],
            eta=eta_value
        )
        task_id_str = task_result.id
        
        if not isinstance(message_record.message_metadata, dict):
            message_record.message_metadata = {}
        message_record.message_metadata['celery_task_id'] = task_id_str
        logger.info(f"✅ Celery task successfully queued. Task ID: {task_id_str} for Message.id: {message_record.id}")

    except Exception as e:
        logger.error(f"❌ Failed to schedule task via Celery for Message.id: {message_record.id}. Exception: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to add message to scheduling queue. Error: {str(e)}")


    # Create an Engagement record to log this manual outbound message
    # The status will be updated by the Celery task once sent/failed
    new_engagement = Engagement(
        customer_id=customer.id,
        message_id=message_record.id, # Link to the Message record created above
        response=None, # No customer response for this specific engagement event
        ai_response=payload.message, # The content of the manual reply
        status=MessageStatusEnum.PROCESSING_SEND.value,   # Indicates it's handed off to Celery; will become 'sent' or 'failed'
        sent_at=None, # Celery task will set this
        business_id=customer.business_id,
        created_at=now_utc # Engagement creation time
    )
    db.add(new_engagement)
    logger.info(f"send_manual_reply: Created Engagement record (ID pending) with status='processing_send' linked to message_record.id={message_record.id}")

    try:
        db.commit()
        db.refresh(new_engagement) # Get the ID of the new_engagement
        logger.info(f"send_manual_reply: Database commit successful. Message_id={message_record.id}, New Engagement_id={new_engagement.id}")
    except Exception as e:
        db.rollback()
        logger.error(f"send_manual_reply: Database commit error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save reply to database.")

    return {
        "status": "success",
        "message": "Reply submitted for sending.", # Informative message for UI
        "message_id": message_record.id, # ID of the Message table record
        "engagement_id": new_engagement.id, # ID of the Engagement table record
        "engagement_status": new_engagement.status # Initial status of the engagement
    }