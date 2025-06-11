#
# Full drop-in file.
# MODIFICATION: Corrects the TypeError in `confirm_event_from_nudge` while preserving all other original functions.
#
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import pytz
import uuid

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models import (
    CoPilotNudge, Customer, BusinessProfile, TargetedEvent, Message,
    NudgeStatusEnum, NudgeTypeEnum, MessageTypeEnum, MessageStatusEnum, Conversation
)
from app.schemas import ConfirmTimedCommitmentPayload
from app.services.twilio_service import TwilioService
from app.celery_tasks import process_scheduled_message_task

logger = logging.getLogger(__name__)

class TargetedEventService:
    """
    Service for managing TargetedEvents, including confirmation and automated reminders.
    """
    def __init__(self, db: Session):
        self.db = db
        # Assuming your TwilioService does not need the db session passed in its constructor
        self.twilio_service = TwilioService(db)

    def _get_or_create_conversation(self, business_id: int, customer_id: int) -> Conversation:
        """Finds an active conversation or creates a new one."""
        conversation = self.db.query(Conversation).filter(
            Conversation.customer_id == customer_id,
            Conversation.business_id == business_id,
            Conversation.status == 'active'
        ).first()

        if not conversation:
            conversation = Conversation(
                id=uuid.uuid4(),
                customer_id=customer_id,
                business_id=business_id,
                status='active',
                started_at=datetime.now(timezone.utc),
                last_message_at=datetime.now(timezone.utc)
            )
            self.db.add(conversation)
            self.db.flush() 
            logger.info(f"Created new conversation for customer {customer_id} during event confirmation.")
        return conversation

    async def _schedule_standard_reminders(
        self,
        event: TargetedEvent,
        conversation: Conversation,
        business_timezone_str: str,
    ) -> list[int]:
        """
        Creates and schedules standard 24-hour and 1-hour SMS reminders for an event.
        (This function is preserved from your original file)
        """
        log_prefix = f"[TargetedEventService][EventID:{event.id}]"
        logger.info(f"{log_prefix} Scheduling standard reminders.")
        
        created_message_ids = []
        now_utc = datetime.now(timezone.utc)
        
        reminders = [
            {"delta": timedelta(hours=24), "template": "Friendly reminder from {business_name} about your '{purpose}' appointment tomorrow at {time}. We're looking forward to seeing you!"},
                {"delta": timedelta(hours=1), "template": "See you soon! Your '{purpose}' appointment with {business_name} is in one hour at {time}."}
            ]

        try:
            business_tz = pytz.timezone(business_timezone_str)
        except pytz.UnknownTimeZoneError:
            logger.error(f"{log_prefix} Invalid business timezone '{business_timezone_str}'. Defaulting to UTC.")
            business_tz = pytz.utc
            
        event_time_local = event.event_datetime_utc.astimezone(business_tz)
        formatted_time = event_time_local.strftime("%I:%M %p %Z").replace(" 0", " ")

        for reminder in reminders:
            scheduled_time_utc = event.event_datetime_utc - reminder["delta"]
            
            if scheduled_time_utc < now_utc:
                logger.info(f"{log_prefix} Skipping reminder scheduled for {scheduled_time_utc.isoformat()} as it's in the past.")
                continue

            message_content = reminder["template"].format(
                business_name=event.business.business_name,
                purpose=event.purpose,
                time=formatted_time
            )
                        
            new_message = Message(
                conversation_id=conversation.id,
                customer_id=event.customer_id,
                business_id=event.business_id,
                content=message_content,
                message_type=MessageTypeEnum.SCHEDULED.value,
                status=MessageStatusEnum.SCHEDULED.value,
                scheduled_time=scheduled_time_utc,
                message_metadata={
                    'source': 'automated_event_reminder',
                    'targeted_event_id': event.id,
                    'reminder_offset': str(reminder["delta"])
                }
            )
            self.db.add(new_message)
            self.db.flush()
            
            try:
                task = process_scheduled_message_task.apply_async(
                    args=[new_message.id],
                    eta=scheduled_time_utc
                )
                new_message.message_metadata['celery_task_id'] = task.id
                created_message_ids.append(new_message.id)
                logger.info(f"{log_prefix} Queued Celery task {task.id} for reminder Message ID {new_message.id} at {scheduled_time_utc.isoformat()}.")
            except Exception as celery_exc:
                logger.error(f"{log_prefix} Failed to queue Celery task for reminder {new_message.id}: {celery_exc}", exc_info=True)
                self.db.rollback()
        
        logger.info(f"{log_prefix} Scheduled {len(created_message_ids)} reminders.")
        return created_message_ids

    async def confirm_event_from_nudge(
        self,
        nudge_id: int,
        payload: ConfirmTimedCommitmentPayload,
        business_id_from_auth: int,
        owner_phone_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Confirms an event, creates records, sends notifications, and schedules reminders.
        """
        log_prefix = f"[TargetedEventService][NudgeID:{nudge_id}]"
        logger.info(f"{log_prefix} Attempting to confirm event.")

        nudge: Optional[CoPilotNudge] = self.db.query(CoPilotNudge).filter(
            CoPilotNudge.id == nudge_id,
            CoPilotNudge.business_id == business_id_from_auth
        ).first()

        if not nudge:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nudge not found.")
        if nudge.nudge_type != NudgeTypeEnum.POTENTIAL_TARGETED_EVENT:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This action is only valid for potential event nudges.")
        if nudge.status != NudgeStatusEnum.ACTIVE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Nudge is not active (status: {nudge.status}).")

        customer: Optional[Customer] = self.db.query(Customer).get(nudge.customer_id)
        business: Optional[BusinessProfile] = self.db.query(BusinessProfile).get(business_id_from_auth)

        if not customer or not business:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer or Business not found.")

        new_event = TargetedEvent(
            business_id=business.id,
            customer_id=customer.id,
            event_datetime_utc=payload.confirmed_datetime_utc,
            purpose=payload.confirmed_purpose,
            status="Owner_Confirmed",
            created_from_nudge_id=nudge.id,
            notes=f"Confirmed from Co-Pilot nudge based on message: '{nudge.message_snippet}'"
        )
        self.db.add(new_event)
        self.db.flush()
        logger.info(f"{log_prefix} Created TargetedEvent (ID: {new_event.id}).")
        
        try:
            business_tz = pytz.timezone(business.timezone)
        except pytz.UnknownTimeZoneError:
            business_tz = pytz.utc
            
        event_time_local = new_event.event_datetime_utc.astimezone(business_tz)
        formatted_datetime = event_time_local.strftime("%B %d at %I:%M %p %Z").replace(" 0", " ")
        
        customer_confirmation_msg = (
            f"Hi {customer.customer_name.split(' ')[0]}, this confirms your appointment for "
            f"'{new_event.purpose}' with {business.business_name} on {formatted_datetime}. "
            f"We look forward to it!"
        )
        
        conversation = self._get_or_create_conversation(business.id, customer.id)
        
        # --- START OF MODIFIED BLOCK ---
        try:
            # Step 1: Call send_sms with only the arguments it accepts.
            # This call now matches your TwilioService signature, removing the extra arguments.
            twilio_sid = await self.twilio_service.send_sms(
                to=customer.phone,
                message_body=customer_confirmation_msg,
                business=business,
                customer=customer
            )

            # Step 2: After sending, create a Message record to log it in the conversation.
            sent_message = Message(
                conversation_id=conversation.id,
                business_id=business.id,
                customer_id=customer.id,
                content=customer_confirmation_msg,
                message_type=MessageTypeEnum.OUTBOUND.value,
                status=MessageStatusEnum.SENT.value,
                sent_at=datetime.now(timezone.utc),
                message_metadata={
                    'source': 'event_confirmation_to_customer',
                    'targeted_event_id': new_event.id,
                    'twilio_sid': twilio_sid # Store the Twilio SID for tracking
                }
            )
            self.db.add(sent_message)
            logger.info(f"{log_prefix} Sent and logged confirmation SMS to customer {customer.id}.")

        except Exception as e:
            logger.error(f"{log_prefix} Failed to send confirmation SMS to customer: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to send confirmation SMS to customer: {e}"
            )
        # --- END OF MODIFIED BLOCK ---

        # MODIFICATION: This block is updated to handle sending internal owner notifications correctly.
        if owner_phone_number:
            owner_notification_msg = (
                f"AI Nudge Co-Pilot: New appointment confirmed for {customer.customer_name} "
                f"regarding '{new_event.purpose}' on {formatted_datetime}."
            )
            try:
                # Call send_sms without the unsupported 'is_internal_notification' argument
                owner_sms_sid = await self.twilio_service.send_sms(
                    to=owner_phone_number,
                    message_body=owner_notification_msg,
                    business=business,
                    is_owner_notification=True 
                    # customer=customer is not needed for an internal notification
                )
                logger.info(f"{log_prefix} Sent confirmation SMS to business owner. SID: {owner_sms_sid}")

                # NEW: Log this internal notification as a special message type for audit purposes
                internal_message = Message(
                    business_id=business.id,
                    content=f"Internal Notification Sent to {owner_phone_number}: {owner_notification_msg}",
                    message_type="internal_notification",
                    status="sent",
                    sent_at=datetime.now(timezone.utc),
                    message_metadata={'source': 'event_confirmation_to_owner', 'twilio_sid': owner_sms_sid}
                )
                self.db.add(internal_message)

            except Exception as e:
                # Log the failure but don't stop the whole process, as the customer notification already succeeded.
                logger.error(f"{log_prefix} Failed to send internal confirmation SMS to business owner: {e}", exc_info=True)
            
        scheduled_reminders = await self._schedule_standard_reminders(new_event, conversation, business.timezone)

        nudge.status = NudgeStatusEnum.ACTIONED.value
        nudge.updated_at = datetime.now(timezone.utc)

        try:
            self.db.commit()
            logger.info(f"{log_prefix} Successfully committed all changes.")
            return {
                "status": "success",
                "message": "Event confirmed, notifications sent, and reminders scheduled.",
                "targeted_event_id": new_event.id,
                "scheduled_reminder_count": len(scheduled_reminders)
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"{log_prefix} Final DB commit failed: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to finalize event confirmation.")