# backend/app/routes/approval_routes.py
import logging
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import update

from app.database import get_db
from app.models import Message, MessageStatusEnum, MessageTypeEnum
# Make sure to import the new BulkActionPayload from your schemas
from app.schemas import ApprovalQueueItem, ApprovePayload, BulkActionPayload
from app.celery_tasks import process_scheduled_message_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["Approvals"])

@router.get("/", response_model=List[ApprovalQueueItem])
def get_approval_queue(business_id: int, db: Session = Depends(get_db)):
    """ Fetches all messages for a business that are in 'pending_approval' status. """
    logger.info(f"Fetching approval queue for business_id: {business_id}")
    try:
        approval_items = (
            db.query(Message)
            .options(joinedload(Message.customer))
            .filter(
                Message.business_id == business_id,
                Message.status == MessageStatusEnum.PENDING_APPROVAL
            )
            .order_by(Message.created_at.desc())
            .all()
        )
        return approval_items
    except Exception as e:
        logger.error(f"DB error fetching approval queue for business_id {business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error while fetching approval queue.")

@router.post("/{message_id}/approve", response_model=ApprovalQueueItem)
def approve_message(
    message_id: int,
    payload: ApprovePayload,
    db: Session = Depends(get_db)
):
    """ Approves a single message from the queue, changing its status and type to 'scheduled'. """
    logger.info(f"Attempting to approve message_id: {message_id}")
    message = db.query(Message).options(joinedload(Message.customer)).filter(Message.id == message_id).first()

    if not message or message.status != MessageStatusEnum.PENDING_APPROVAL:
        raise HTTPException(status_code=404, detail="Message not found or not pending approval.")

    if payload.content is not None:
        message.content = payload.content
    
    send_time = payload.send_datetime_utc or (datetime.now(timezone.utc) + timedelta(seconds=15))
    
    message.status = MessageStatusEnum.SCHEDULED
    message.message_type = MessageTypeEnum.SCHEDULED
    message.scheduled_time = send_time
    
    try:
        task = process_scheduled_message_task.apply_async(args=[message.id], eta=send_time)
        metadata = message.message_metadata or {}
        metadata['celery_task_id'] = task.id
        message.message_metadata = metadata
        db.commit()
        db.refresh(message)
        logger.info(f"Successfully approved and queued message {message_id}.")
        return message
    except Exception as e:
        db.rollback()
        logger.error(f"Celery task queueing failed for message {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to schedule message delivery.")

@router.post("/{message_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_message(message_id: int, db: Session = Depends(get_db)):
    """ Rejects a single message from the queue. """
    logger.info(f"Attempting to reject message_id: {message_id}")
    db.query(Message).filter(Message.id == message_id, Message.status == MessageStatusEnum.PENDING_APPROVAL).update({"status": MessageStatusEnum.REJECTED})
    db.commit()
    return None

# --- NEW ENDPOINT FOR BULK ACTIONS ---
@router.post("/bulk-action", status_code=status.HTTP_200_OK)
def bulk_action_messages(payload: BulkActionPayload, db: Session = Depends(get_db)):
    """
    Approves or rejects a list of messages in bulk.
    """
    if not payload.message_ids:
        raise HTTPException(status_code=400, detail="No message IDs provided.")

    logger.info(f"Performing bulk action '{payload.action}' on {len(payload.message_ids)} messages.")

    if payload.action == 'reject':
        stmt = (
            update(Message)
            .where(Message.id.in_(payload.message_ids), Message.status == MessageStatusEnum.PENDING_APPROVAL)
            .values(status=MessageStatusEnum.REJECTED)
        )
        result = db.execute(stmt)
        db.commit()
        return {"status": "success", "message": f"{result.rowcount} messages rejected."}

    elif payload.action == 'approve':
        send_time = payload.send_datetime_utc or (datetime.now(timezone.utc) + timedelta(seconds=15))
        
        messages_to_approve = db.query(Message).filter(
            Message.id.in_(payload.message_ids),
            Message.status == MessageStatusEnum.PENDING_APPROVAL
        ).all()

        if not messages_to_approve:
            return {"status": "success", "message": "No valid messages found to approve."}

        for message in messages_to_approve:
            message.status = MessageStatusEnum.SCHEDULED
            message.message_type = MessageTypeEnum.SCHEDULED
            message.scheduled_time = send_time
            try:
                task = process_scheduled_message_task.apply_async(args=[message.id], eta=send_time)
                metadata = message.message_metadata or {}
                metadata['celery_task_id'] = task.id
                message.message_metadata = metadata
            except Exception as e:
                db.rollback()
                logger.error(f"Celery task queueing failed during bulk approve for message {message.id}: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Failed to schedule message ID {message.id}.")
        
        db.commit()
        return {"status": "success", "message": f"{len(messages_to_approve)} messages scheduled successfully."}

    else:
        raise HTTPException(status_code=400, detail="Invalid action specified.")
