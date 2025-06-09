# backend/app/services/follow_up_plan_service.py
import logging
from datetime import datetime, timezone # Added timezone
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import pytz

from app.models import (
    CoPilotNudge,
    Customer,
    BusinessProfile,
    Message,
    Conversation,
    NudgeStatusEnum,
    NudgeTypeEnum,
    MessageTypeEnum,
    MessageStatusEnum,
)
from app.schemas import ActivateEngagementPlanPayload
from app.celery_tasks import process_scheduled_message_task
from app.celery_app import celery_app # Import for revoking tasks

logger = logging.getLogger(__name__)

class FollowUpPlanService:
    """
    Service for handling actions related to AI-drafted Follow-up Nudge Plans.
    """
    def __init__(self, db: Session):
        self.db = db

    async def activate_plan_from_nudge(
        self,
        nudge_id: int,
        payload: ActivateEngagementPlanPayload,
        business_id_from_auth: int
    ) -> Dict[str, Any]:
        """
        Activates a multi-message follow-up plan from a Co-Pilot nudge.
        This involves creating and scheduling multiple 'Message' records based on the payload.
        """
        log_prefix = f"[FollowUpPlanService][NudgeID:{nudge_id}]"
        logger.info(f"{log_prefix} Attempting to activate follow-up nudge plan.")

        # --- 1. Validate the Nudge ---
        nudge: Optional[CoPilotNudge] = self.db.query(CoPilotNudge).filter(
            CoPilotNudge.id == nudge_id,
            CoPilotNudge.business_id == business_id_from_auth
        ).first()

        if not nudge:
            logger.warning(f"{log_prefix} Nudge not found or does not belong to business {business_id_from_auth}.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nudge not found.")

        if nudge.nudge_type != NudgeTypeEnum.STRATEGIC_ENGAGEMENT_OPPORTUNITY:
            logger.warning(f"{log_prefix} Nudge type is '{nudge.nudge_type}', expected '{NudgeTypeEnum.STRATEGIC_ENGAGEMENT_OPPORTUNITY}'.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This action is only valid for STRATEGIC_ENGAGEMENT_OPPORTUNITY nudges.")

        if nudge.status != NudgeStatusEnum.ACTIVE:
            logger.warning(f"{log_prefix} Nudge status is '{nudge.status}', expected '{NudgeStatusEnum.ACTIVE}'. Cannot action.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Nudge is not active (status: {nudge.status}).")
        
        if nudge.customer_id != payload.customer_id:
             logger.error(f"{log_prefix} Customer ID mismatch. Nudge has customer_id {nudge.customer_id}, but payload has {payload.customer_id}.")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer ID mismatch.")

        # --- 2. Get Conversation ---
        conversation = self.db.query(Conversation).filter(
            Conversation.customer_id == payload.customer_id,
            Conversation.business_id == business_id_from_auth,
            Conversation.status == 'active'
        ).first()

        if not conversation:
            logger.info(f"{log_prefix} No active conversation found for customer {payload.customer_id}. Creating a new one.")
            conversation = Conversation(
                customer_id=payload.customer_id,
                business_id=business_id_from_auth,
                status='active'
            )
            self.db.add(conversation)
            self.db.flush() 

        # --- 3. Intelligent Integration (MVP: Check for Overlaps) ---
        now_utc = datetime.now(pytz.utc)
        existing_future_messages_count = self.db.query(Message).filter(
            Message.customer_id == payload.customer_id,
            Message.status == MessageStatusEnum.SCHEDULED.value,
            Message.scheduled_time > now_utc
        ).count()
        
        if existing_future_messages_count > 0:
            logger.warning(f"{log_prefix} Customer {payload.customer_id} already has {existing_future_messages_count} future message(s) scheduled. Proceeding with adding new plan messages.")
        
        # --- 4. Create and Schedule Messages ---
        created_message_ids = []
        scheduled_tasks = []

        for message_data in payload.messages:
            scheduled_time = message_data.send_datetime_utc
            if scheduled_time.tzinfo is None:
                scheduled_time = pytz.utc.localize(scheduled_time)
            
            if scheduled_time < now_utc:
                logger.warning(f"{log_prefix} Scheduled time {scheduled_time.isoformat()} for a message is in the past. Skipping this message.")
                continue

            new_message = Message(
                conversation_id=conversation.id,
                customer_id=payload.customer_id,
                business_id=business_id_from_auth,
                content=message_data.text,
                message_type=MessageTypeEnum.SCHEDULED.value,
                status=MessageStatusEnum.SCHEDULED.value,
                scheduled_time=scheduled_time,
                message_metadata={
                    'source': 'follow_up_nudge_plan', # Updated source name
                    'nudge_id': nudge.id,
                    'plan_objective': nudge.ai_suggestion_payload.get('plan_objective') if nudge.ai_suggestion_payload else None
                }
            )
            self.db.add(new_message)
            self.db.flush()
            
            try:
                task = process_scheduled_message_task.apply_async(
                    args=[new_message.id],
                    eta=scheduled_time
                )
                new_message.message_metadata['celery_task_id'] = task.id
                created_message_ids.append(new_message.id)
                scheduled_tasks.append(task.id)
                logger.info(f"{log_prefix} Queued Celery task {task.id} for Message ID {new_message.id} to be sent at {scheduled_time.isoformat()}.")
            except Exception as celery_exc:
                logger.error(f"{log_prefix} Failed to queue Celery task for Message ID {new_message.id}: {celery_exc}", exc_info=True)
                self.db.rollback()
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to schedule messages in the background queue.")


        # --- 5. Update Nudge Status ---
        nudge.status = NudgeStatusEnum.ACTIONED
        nudge.updated_at = datetime.now(timezone.utc)

        try:
            self.db.commit()
            logger.info(f"{log_prefix} Successfully activated plan. Created {len(created_message_ids)} message(s). Nudge status updated to ACTIONED.")
            return {
                "status": "success",
                "message": f"Successfully activated follow-up nudge plan. {len(created_message_ids)} message(s) have been scheduled.",
                "created_message_ids": created_message_ids,
                "celery_task_ids": scheduled_tasks
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"{log_prefix} Final DB commit failed after queueing Celery tasks. Attempting to revoke tasks. Error: {e}", exc_info=True)
            # Attempt to revoke tasks that were queued but not committed
            for task_id in scheduled_tasks:
                try:
                    celery_app.control.revoke(task_id, terminate=True)
                except Exception as revoke_exc:
                    logger.error(f"{log_prefix} Failed to revoke Celery task {task_id}: {revoke_exc}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to finalize plan activation due to a database error.")
