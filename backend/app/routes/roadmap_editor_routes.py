# backend/app/routes/roadmap_editor_routes.py
import logging
from typing import List
from datetime import datetime
import pytz
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RoadmapMessage, Message, Customer, Conversation, MessageStatusEnum, MessageTypeEnum
from app.schemas import ScheduleEditedRoadmapsRequest
from app.celery_tasks import process_scheduled_message_task
from app.celery_app import celery_app

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Roadmap Editor"])

@router.post("/schedule-edited", status_code=status.HTTP_200_OK)
def schedule_edited_roadmaps(
    payload: ScheduleEditedRoadmapsRequest,
    db: Session = Depends(get_db)
):
    """
    Receives a batch of edited roadmap messages, updates them in the database,
    and schedules them for delivery. This is a single transactional endpoint.
    """
    if not payload.edited_messages:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No messages provided to schedule.")

    log_prefix = "[RoadmapEditor]"
    logger.info(f"{log_prefix} Received request to schedule {len(payload.edited_messages)} edited messages.")

    scheduled_count = 0
    failed_items = []
    
    # Fetch all roadmap messages and related customers in fewer queries
    message_ids = [item.roadmap_message_id for item in payload.edited_messages]
    roadmap_messages_orm = db.query(RoadmapMessage).filter(RoadmapMessage.id.in_(message_ids)).all()
    roadmap_map = {msg.id: msg for msg in roadmap_messages_orm}
    
    customer_ids = {msg.customer_id for msg in roadmap_messages_orm}
    customers = db.query(Customer).filter(Customer.id.in_(customer_ids)).all()
    customer_map = {c.id: c for c in customers}

    for item in payload.edited_messages:
        roadmap_msg = roadmap_map.get(item.roadmap_message_id)
        
        # --- Pre-flight checks for each item ---
        if not roadmap_msg:
            failed_items.append({"id": item.roadmap_message_id, "reason": "Message not found."})
            continue
        if roadmap_msg.status == "superseded":
            failed_items.append({"id": item.roadmap_message_id, "reason": "Message has already been scheduled."})
            continue
            
        customer = customer_map.get(roadmap_msg.customer_id)
        if not customer or not customer.opted_in:
            failed_items.append({"id": item.roadmap_message_id, "reason": "Customer not found or has opted out."})
            continue

        # --- Update and Schedule Logic ---
        try:
            # 1. Update the original RoadmapMessage with final content and time
            roadmap_msg.smsContent = item.content
            roadmap_msg.send_datetime_utc = item.send_datetime_utc

            # 2. Find or create conversation
            conversation = db.query(Conversation).filter(Conversation.customer_id == customer.id, Conversation.business_id == customer.business_id, Conversation.status == 'active').first()
            if not conversation:
                conversation = Conversation(id=uuid.uuid4(), customer_id=customer.id, business_id=customer.business_id, status='active')
                db.add(conversation)
                db.flush()

            # 3. Create the definitive Message record
            new_message = Message(
                conversation_id=conversation.id,
                customer_id=customer.id,
                business_id=customer.business_id,
                content=item.content,
                message_type=MessageTypeEnum.SCHEDULED,
                status=MessageStatusEnum.SCHEDULED,
                scheduled_time=item.send_datetime_utc,
                message_metadata={'source': 'roadmap_editor', 'roadmap_id': roadmap_msg.id}
            )
            db.add(new_message)
            db.flush()

            # 4. Schedule with Celery
            eta_value = item.send_datetime_utc
            if eta_value.tzinfo is None:
                eta_value = pytz.utc.localize(eta_value)
            
            task = process_scheduled_message_task.apply_async(args=[new_message.id], eta=eta_value)
            new_message.message_metadata['celery_task_id'] = task.id
            
            # 5. Mark original RoadmapMessage as processed
            roadmap_msg.status = "superseded"
            roadmap_msg.message_id = new_message.id
            
            scheduled_count += 1
        except Exception as e:
            logger.error(f"{log_prefix} Failed to process message ID {item.roadmap_message_id}. Error: {e}", exc_info=True)
            failed_items.append({"id": item.roadmap_message_id, "reason": str(e)})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        # If commit fails, we should ideally try to revoke any tasks that were queued.
        # This is a complex recovery pattern; for now, we raise a server error.
        logger.error(f"{log_prefix} Final DB commit failed. Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error occurred while finalizing schedule.")

    return {
        "status": "completed",
        "scheduled_count": scheduled_count,
        "failed_count": len(failed_items),
        "failures": failed_items
    }