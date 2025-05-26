# backend/app/routes/roadmap_workflow_routes.py

print("✅ roadmap_workflow_routes.py loaded")

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc, cast, Integer
from datetime import datetime, timezone
from app.database import get_db
from app.models import RoadmapMessage, Message, Customer, Conversation, MessageTypeEnum, MessageStatusEnum, SenderTypeEnum # Added Enum imports
from app.celery_tasks import process_scheduled_message_task
import logging
import uuid
import pytz


logger = logging.getLogger(__name__)

router = APIRouter()

# 🔵 Route: PUT /roadmap-workflow/{roadmap_id}/schedule
# Schedules a single roadmap message for a customer.
@router.put("/{roadmap_id}/schedule")
def schedule_message(roadmap_id: int, db: Session = Depends(get_db)):
    # 🔹 Step 1: Fetch the roadmap message by ID
    msg = db.query(RoadmapMessage).filter(RoadmapMessage.id == roadmap_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Roadmap message not found")

    # 🔹 Step 2: Validate the send time exists
    if not msg.send_datetime_utc:
        raise HTTPException(status_code=400, detail="Missing send time for roadmap message")

    # 🔹 Step 3: Check if already scheduled
    if msg.status == MessageStatusEnum.SCHEDULED.value: # Using enum value
        return {"status": "already scheduled"}

    # 🔹 Step 4: Fetch the customer and check opt-in status
    customer = db.query(Customer).filter(Customer.id == msg.customer_id).first()
    if not customer or not customer.opted_in:
        raise HTTPException(status_code=403, detail="Customer has not opted in to receive SMS")

    # 🔹 Step 5: Fetch or create an active conversation
    conversation = db.query(Conversation).filter(
        Conversation.customer_id == customer.id,
        Conversation.business_id == msg.business_id,
        Conversation.status == 'active'
    ).first()

    if not conversation:
        conversation = Conversation(
            id=uuid.uuid4(),
            customer_id=customer.id,
            business_id=msg.business_id,
            started_at=datetime.now(pytz.UTC),
            last_message_at=datetime.now(pytz.UTC),
            status='active'
        )
        db.add(conversation)
        db.flush()

    # 🔹 Step 6: Check for existing scheduled message linked to roadmap message
    existing_message = db.query(Message).filter(
    Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE, # Using enum member
    Message.message_metadata != None,    # Ensure metadata is not null
    cast(Message.message_metadata.op('->>')('roadmap_id'), Integer) == msg.id
    ).first()

    if not existing_message:
        # 🔹 Step 7: Create and add new scheduled message
        message = Message(
            conversation_id=conversation.id,
            customer_id=msg.customer_id,
            business_id=msg.business_id,
            content=msg.smsContent,
            message_type=MessageTypeEnum.SCHEDULED_MESSAGE, # Using enum member
            status=MessageStatusEnum.SCHEDULED, # Using enum member
            sender_type=SenderTypeEnum.BUSINESS, # Added sender_type
            scheduled_send_at=msg.send_datetime_utc, # Corrected from scheduled_time
            message_metadata={
                'source': 'roadmap',
                'roadmap_id': msg.id
            }
        )
        db.add(message)
        db.flush()

        # 🔹 Step 8: TRY scheduling with Celery first
        try:
            logger.info(f"📤 Scheduling task 'process_scheduled_message_task' via Celery: Message id={message.id}, ETA={msg.send_datetime_utc}")
            # Call the correct task with message ID and eta
            process_scheduled_message_task.apply_async(
                args=[message.id], # Pass the ID of the Message record
                eta=msg.send_datetime_utc
            )
        except Exception as e:
            logger.error(f"❌ Failed to schedule SMS task for message {message.id}: {str(e)}")
            # Optionally rollback or update message status here if scheduling fails critically
            raise HTTPException(status_code=500, detail="Failed to add message to scheduling queue. Please retry.")

        # 🔹 Step 9: ONLY IF Celery succeeds, update status and commit
        msg.status = MessageStatusEnum.SCHEDULED.value # Using enum value
        msg.message_id = message.id
        db.commit()

        return {
            "status": "scheduled",
            "message_id": message.id,
            "message": {
                "id": message.id,
                "customer_name": customer.customer_name,
                "smsContent": message.content,
                "send_datetime_utc": message.scheduled_send_at.isoformat() if message.scheduled_send_at else None, # Corrected to scheduled_send_at
                "status": message.status,
                "source": message.message_metadata.get('source', 'scheduled')
            }
        }

    msg.status = MessageStatusEnum.SCHEDULED.value # Using enum value
    db.commit()
    return {"status": "already scheduled"}


# 🔵 Route: POST /roadmap-workflow/approve-all/{customer_id}
# Approves and schedules all pending roadmap messages for a customer.
@router.post("/approve-all/{customer_id}")
def approve_all(customer_id: int, db: Session = Depends(get_db)):
    now_utc = datetime.now(timezone.utc)

    # 🔹 Step 3: Fetch all pending roadmap messages
    messages = db.query(RoadmapMessage).filter(
        and_(
            RoadmapMessage.customer_id == customer_id,
            RoadmapMessage.send_datetime_utc != None,
            RoadmapMessage.send_datetime_utc >= now_utc,
            RoadmapMessage.status == MessageStatusEnum.PENDING_REVIEW.value # Using enum value
        )
    ).all()

    # 🔹 Step 1: Validate customer existence and opt-in status
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer or not customer.opted_in:
        return {"scheduled": 0, "skipped": len(messages), "reason": "Customer has not opted in"}

    # 🔹 Step 2: Fetch or create an active conversation
    conversation = db.query(Conversation).filter(
        Conversation.customer_id == customer.id,
        Conversation.business_id == customer.business_id,
        Conversation.status == 'active'
    ).first()

    if not conversation:
        conversation = Conversation(
            id=uuid.uuid4(),
            customer_id=customer.id,
            business_id=customer.business_id,
            started_at=datetime.now(pytz.UTC),
            last_message_at=datetime.now(pytz.UTC),
            status='active'
        )
        db.add(conversation)
        db.flush()

    new_scheduled_count = 0

    # 🔹 Step 4: Loop over messages and attempt scheduling
    for msg in messages:
        exists = db.query(Message).filter(
            Message.message_metadata['roadmap_id'].cast(Integer) == msg.id,
            Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE # Using enum member
        ).first()

        if not exists:
            message = Message(
                conversation_id=conversation.id,
                customer_id=msg.customer_id,
                business_id=msg.business_id,
                content=msg.smsContent,
                message_type=MessageTypeEnum.SCHEDULED_MESSAGE, # Using enum member
                status=MessageStatusEnum.SCHEDULED, # Using enum member
                sender_type=SenderTypeEnum.BUSINESS, # Added sender_type
                scheduled_send_at=msg.send_datetime_utc, # Corrected from scheduled_time
                message_metadata={
                    'source': 'roadmap',
                    'roadmap_id': msg.id
                }
            )
            db.add(message)
            db.flush()

            # 🔹 Step 5: Try to schedule message with Celery
            try:
                logger.info(f"📤 Scheduling task 'process_scheduled_message_task' via Celery: Message id={message.id}, ETA={msg.send_datetime_utc}")
                # Call the correct task with message ID and eta
                process_scheduled_message_task.apply_async(
                    args=[message.id], # Pass the ID of the Message record
                    eta=msg.send_datetime_utc
                )
            except Exception as e:
                logger.error(f"❌ Failed to schedule SMS task for message {message.id}: {str(e)}")
                # If adding to queue fails, maybe don't update the status or log specifically
                continue # Skip updating status for this message if scheduling fails

            # 🔹 Step 6: If successful, update message and roadmap status
            msg.status = MessageStatusEnum.SCHEDULED.value # Using enum value
            msg.message_id = message.id
            new_scheduled_count += 1

    # 🔹 Step 7: Commit changes
    db.commit()

    # 🔹 Step 8: Return summary
    return {
        "scheduled": new_scheduled_count,
        "skipped": len(messages) - new_scheduled_count,
        "reason": "Already scheduled" if len(messages) - new_scheduled_count > 0 else None
    }

# 🔵 Route: PUT /roadmap-workflow/update-time/{id}
# Updates the scheduled time for a roadmap or scheduled message.
@router.put("/update-time/{id}")
def update_message_time(
    id: int,
    source: str = Query(...),
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    # 🔹 Step 1: Validate and parse new time input
    try:
        new_time = datetime.fromisoformat(payload["send_datetime_utc"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid time format")

    new_content = payload.get("smsContent")

    # 🔹 Step 2: Update roadmap or scheduled message time and optionally content
    if source == "roadmap":
        message = db.query(RoadmapMessage).filter(RoadmapMessage.id == id).first()
        if not message:
            raise HTTPException(status_code=404, detail="Roadmap message not found")

        message.send_datetime_utc = new_time
        if new_content:
            message.smsContent = new_content

        scheduled = db.query(Message).filter(
            Message.message_metadata['roadmap_id'].cast(Integer) == id,
            Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE # Using enum member
        ).first()

        if scheduled:
            scheduled.scheduled_send_at = new_time # Corrected from scheduled_time
            if new_content:
                scheduled.content = new_content

    else:
        message = db.query(Message).filter(
            Message.id == id,
            Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE # Using enum member
        ).first()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        message.scheduled_send_at = new_time # Corrected from scheduled_time
        if new_content:
            message.content = new_content

        if message.message_metadata and 'roadmap_id' in message.message_metadata:
            roadmap = db.query(RoadmapMessage).filter(
                RoadmapMessage.id == message.message_metadata['roadmap_id']
            ).first()
            if roadmap:
                roadmap.send_datetime_utc = new_time
                if new_content:
                    roadmap.smsContent = new_content

    # 🔹 Step 3: Commit changes
    db.commit()
    return {"status": "success", "new_time": new_time.isoformat()}

# 🔵 Route: DELETE /roadmap-workflow/{id}
# Deletes a roadmap or scheduled message.
@router.delete("/{id}")
def delete_message(id: int, source: str = Query(...), db: Session = Depends(get_db)):
    # 🔹 Step 1: Determine source type (roadmap or scheduled)
    if source == "roadmap":
        message = db.query(RoadmapMessage).filter(RoadmapMessage.id == id).first()
        if not message:
            raise HTTPException(status_code=404, detail="Roadmap message not found")

        scheduled = db.query(Message).filter(
            Message.message_metadata['roadmap_id'].cast(Integer) == id,
            Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE # Using enum member
        ).first()

        # 🔹 Step 2: Fetch and delete corresponding records
        if scheduled:
            db.delete(scheduled)

        db.delete(message)
        # 🔹 Step 3: Commit changes
        db.commit()
        # 🔹 Step 4: Return success payload
        return {"success": True, "deleted_from": "roadmap", "id": id}

    else:
        message = db.query(Message).filter(
            Message.id == id,
            Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE # Using enum member
        ).first()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        if message.message_metadata and 'roadmap_id' in message.message_metadata:
            roadmap = db.query(RoadmapMessage).filter(
                RoadmapMessage.id == message.message_metadata['roadmap_id']
            ).first()
            if roadmap:
                db.delete(roadmap)

        db.delete(message)
        # 🔹 Step 3: Commit changes
        db.commit()
        # 🔹 Step 4: Return success payload
        return {"success": True, "deleted_from": "scheduled", "id": id}