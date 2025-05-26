# backend/app/services/message_service.py

from enum import Enum
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any # Added Any for broader dict compatibility
import logging
import uuid

# Make sure to import AsyncSession and select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, delete, update # Added update
from app.models import (
    Message, RoadmapMessage, Customer, ConsentLog, Conversation, BusinessProfile,
    MessageTypeEnum as GlobalMessageTypeEnum,
    MessageStatusEnum as GlobalMessageStatusEnum,
    OptInStatus as GlobalOptInStatus,
    SenderTypeEnum as GlobalSenderTypeEnum
)
from app import schemas # For using schemas.MessageUpdate
from app.timezone_utils import get_utc_now # For consistency in getting current UTC time
# REMOVED: from app.services.message_service import MessageService # <<< THIS LINE WAS REMOVED

logger = logging.getLogger(__name__)

# --- STANDALONE FUNCTION (from your file) ---
async def get_conversation_id(db: AsyncSession, business_id: int, customer_id: int) -> str:
    """
    Retrieves the active conversation ID for a given business and customer.
    If no active conversation exists, creates a new one.
    Returns the conversation ID as a string.
    Flushes changes within this function; commit is handled by the caller using this in a broader transaction.
    """
    now_utc_aware = get_utc_now()
    log_prefix = f"[get_conversation_id(B:{business_id},C:{customer_id})]"

    business_stmt = select(BusinessProfile).where(BusinessProfile.id == business_id)
    business_result = await db.execute(business_stmt)
    business = business_result.scalars().first()
    if not business:
        logger.error(f"{log_prefix} Business not found.")
        raise ValueError(f"Business with ID {business_id} not found.")

    customer_stmt = select(Customer).where(Customer.id == customer_id, Customer.business_id == business_id)
    customer_result = await db.execute(customer_stmt)
    customer = customer_result.scalars().first()
    if not customer:
        logger.error(f"{log_prefix} Customer not found for this business.")
        raise ValueError(f"Customer with ID {customer_id} not found for business {business_id}.")

    conversation_stmt = select(Conversation).filter(
        Conversation.customer_id == customer_id,
        Conversation.business_id == business_id,
    ).order_by(desc(Conversation.last_message_at))
    
    conversation_result = await db.execute(conversation_stmt)
    conversation = conversation_result.scalars().first()

    try:
        if conversation and conversation.status == 'active':
            logger.info(f"{log_prefix} Found existing active conversation ID: {conversation.id}")
            conversation.last_message_at = now_utc_aware
            await db.flush()
            return str(conversation.id)
        else:
            if conversation:
                logger.info(f"{log_prefix} Found existing conversation (ID: {conversation.id}, Status: '{conversation.status}'). Creating new active conversation as per policy.")
            
            new_conversation_id_obj = uuid.uuid4()
            new_conversation = Conversation(
                id=new_conversation_id_obj,
                customer_id=customer_id,
                business_id=business_id,
                started_at=now_utc_aware,
                last_message_at=now_utc_aware,
                status='active'
            )
            db.add(new_conversation)
            await db.flush()
            logger.info(f"{log_prefix} Created new active conversation ID: {new_conversation_id_obj}")
            return str(new_conversation_id_obj)
    except Exception as e:
        logger.error(f"{log_prefix} Error getting/creating conversation ID: {e}", exc_info=True)
        raise


class MessageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_customer_messages(
        self,
        customer_id: int,
        include_past: bool = False
    ) -> Dict:
        now_utc = get_utc_now()

        roadmap_stmt = select(RoadmapMessage).filter(
            and_(
                RoadmapMessage.customer_id == customer_id,
                RoadmapMessage.send_datetime_utc != None,
                RoadmapMessage.status != GlobalMessageStatusEnum.DELETED.value
            )
        )

        scheduled_msg_stmt = select(Message).filter(
            Message.customer_id == customer_id,
            Message.message_type == GlobalMessageTypeEnum.SCHEDULED_MESSAGE.value,
            Message.status == GlobalMessageStatusEnum.SCHEDULED.value
        )

        if not include_past:
            roadmap_stmt = roadmap_stmt.filter(RoadmapMessage.send_datetime_utc >= now_utc)
            scheduled_msg_stmt = scheduled_msg_stmt.filter(Message.scheduled_send_at >= now_utc)

        roadmap_result = await self.db.execute(roadmap_stmt)
        scheduled_result = await self.db.execute(scheduled_msg_stmt)

        return {
            "roadmap": roadmap_result.scalars().all(),
            "scheduled_messages": scheduled_result.scalars().all(),
            "consent_status": await self._get_customer_consent_status(customer_id)
        }

    async def schedule_message(
        self,
        customer_id: int,
        business_id: int,
        content: str,
        scheduled_send_at: Optional[datetime] = None,
        sender_type: GlobalSenderTypeEnum = GlobalSenderTypeEnum.BUSINESS,
        source: Optional[str] = None
    ) -> Message:
        customer_stmt = select(Customer).filter(Customer.id == customer_id)
        customer_result = await self.db.execute(customer_stmt)
        customer = customer_result.scalars().first()

        if not customer or customer.sms_opt_in_status != GlobalOptInStatus.OPTED_IN.value:
            logger.warning(f"MessageService: Cannot schedule message. Customer {customer_id} not found or not opted-in (Status: {customer.sms_opt_in_status if customer else 'N/A'}).")
            raise ValueError("Customer has not opted in to receive SMS or does not exist.")

        if not scheduled_send_at:
            logger.error("MessageService: scheduled_send_at must be provided to schedule a message.")
            raise ValueError("scheduled_send_at is required for scheduling a message.")
        
        if scheduled_send_at.tzinfo is None or scheduled_send_at.tzinfo.utcoffset(scheduled_send_at) is None:
            logger.warning(f"MessageService: Naive datetime for scheduled_send_at '{scheduled_send_at}', assuming UTC.")
            scheduled_send_at = scheduled_send_at.replace(tzinfo=timezone.utc)
        else:
            scheduled_send_at = scheduled_send_at.astimezone(timezone.utc)

        message = await self.create_message(
            customer_id=customer_id,
            business_id=business_id,
            content=content,
            scheduled_send_at=scheduled_send_at,
            message_type=GlobalMessageTypeEnum.SCHEDULED_MESSAGE,
            status=GlobalMessageStatusEnum.SCHEDULED,
            sender_type=sender_type,
            source=source or "manual_schedule"
        )
        logger.info(f"MessageService: Message (ID: {message.id}) scheduled for customer {customer_id} at {scheduled_send_at.isoformat()}.")
        return message

    async def create_message(
        self,
        customer_id: int,
        business_id: int,
        content: str,
        conversation_id: Optional[uuid.UUID] = None,
        message_type: Optional[GlobalMessageTypeEnum] = GlobalMessageTypeEnum.OUTBOUND,
        status: Optional[GlobalMessageStatusEnum] = GlobalMessageStatusEnum.PENDING,
        scheduled_send_at: Optional[datetime] = None,
        message_metadata: Optional[Dict[str, Any]] = None,
        sender_type: GlobalSenderTypeEnum = GlobalSenderTypeEnum.BUSINESS,
        is_hidden: bool = False,
        twilio_message_sid: Optional[str] = None,
        source: Optional[str] = None
    ) -> Message:
        if not conversation_id:
            try:
                conv_id_str = await get_conversation_id(self.db, business_id, customer_id)
                conversation_id = uuid.UUID(conv_id_str)
            except ValueError as ve:
                logger.error(f"MessageService: Failed to get/create conversation ID for B:{business_id}, C:{customer_id}. Error: {ve}")
                raise

        effective_message_type = message_type if message_type is not None else GlobalMessageTypeEnum.OUTBOUND
        effective_status = status if status is not None else GlobalMessageStatusEnum.PENDING

        message = Message(
            conversation_id=conversation_id,
            customer_id=customer_id,
            business_id=business_id,
            content=content,
            message_type=effective_message_type,
            status=effective_status,
            scheduled_send_at=scheduled_send_at,
            message_metadata=message_metadata,
            sender_type=sender_type,
            is_hidden=is_hidden,
            twilio_message_sid=twilio_message_sid,
            source=source,
            created_at=get_utc_now(),
            updated_at=get_utc_now()
        )
        self.db.add(message)
        try:
            await self.db.commit()
            await self.db.refresh(message)
            logger.info(f"MessageService: Message (ID: {message.id}) created for B:{business_id}, C:{customer_id}.")
            return message
        except Exception as e:
            await self.db.rollback()
            logger.error(f"MessageService: Error creating message for C:{customer_id}. DB Rollback. Error: {e}", exc_info=True)
            raise

    async def get_message_by_id_for_business(self, message_id: int, business_id: int) -> Optional[Message]:
        stmt = select(Message).filter(
            Message.id == message_id,
            Message.business_id == business_id
        )
        result = await self.db.execute(stmt)
        message = result.scalars().first()
        if not message:
            logger.warning(f"MessageService: Message ID {message_id} not found or not authorized for Business ID {business_id}.")
        return message

    async def update_message_status(self, message_id: int, new_status: GlobalMessageStatusEnum, sent_at_val: Optional[datetime] = None) -> Optional[Message]:
        # This method should ideally also take business_id for authorization if called directly from routes
        # For now, assuming it's called internally or after auth.
        stmt_get = select(Message).where(Message.id == message_id)
        result_get = await self.db.execute(stmt_get)
        message_to_update = result_get.scalar_one_or_none()

        if message_to_update:
            message_to_update.status = new_status
            if new_status == GlobalMessageStatusEnum.SENT:
                message_to_update.sent_at = sent_at_val if sent_at_val else get_utc_now()
            message_to_update.updated_at = get_utc_now()
            try:
                await self.db.commit()
                await self.db.refresh(message_to_update)
                logger.info(f"MessageService: Message (ID: {message_to_update.id}) status updated to {new_status.value}.")
                return message_to_update
            except Exception as e:
                await self.db.rollback()
                logger.error(f"MessageService: Error updating message status for ID {message_id}. DB Rollback. Error: {e}", exc_info=True)
                raise
        logger.warning(f"MessageService: Message ID {message_id} not found for status update.")
        return None

    async def update_message_content_schedule(
        self,
        message_id: int,
        business_id: int,
        message_data: schemas.MessageUpdate
    ) -> Optional[Message]:
        logger.info(f"MessageService: Attempting to update content/schedule for message ID {message_id}, Business ID {business_id}.")
        db_message = await self.get_message_by_id_for_business(message_id, business_id)

        if not db_message:
            return None

        if not (db_message.message_type == GlobalMessageTypeEnum.SCHEDULED_MESSAGE and \
                db_message.status == GlobalMessageStatusEnum.SCHEDULED):
            logger.warning(f"MessageService: Message ID {message_id} is not an editable scheduled message (Type: {db_message.message_type}, Status: {db_message.status}). Update denied.")
            raise ValueError("Only messages of type 'scheduled_message' with status 'scheduled' can have their content/schedule updated this way.")

        update_payload = message_data.model_dump(exclude_unset=True)
        changes_made = False

        if "content" in update_payload and update_payload["content"] is not None:
            db_message.content = update_payload["content"]
            changes_made = True
            logger.info(f"MessageService: Message ID {message_id} content updated.")

        if "scheduled_send_at" in update_payload and update_payload["scheduled_send_at"] is not None:
            new_scheduled_time = update_payload["scheduled_send_at"]
            if new_scheduled_time.tzinfo is None or new_scheduled_time.tzinfo.utcoffset(new_scheduled_time) is None:
                new_scheduled_time = new_scheduled_time.replace(tzinfo=timezone.utc)
            else:
                new_scheduled_time = new_scheduled_time.astimezone(timezone.utc)
            
            db_message.scheduled_send_at = new_scheduled_time
            changes_made = True
            logger.info(f"MessageService: Message ID {message_id} scheduled_send_at updated to {new_scheduled_time.isoformat()}.")
        
        if "status" in update_payload and update_payload["status"] is not None:
            new_status_val = GlobalMessageStatusEnum(update_payload["status"])
            if new_status_val != GlobalMessageStatusEnum.SCHEDULED:
                logger.warning(f"MessageService: Status for message {message_id} changed from SCHEDULED to {new_status_val.value} via content/schedule update method.")
            db_message.status = new_status_val
            changes_made = True

        if changes_made:
            db_message.updated_at = get_utc_now()
            try:
                await self.db.commit()
                await self.db.refresh(db_message)
                logger.info(f"MessageService: Message ID {db_message.id} successfully updated.")
                return db_message
            except Exception as e:
                await self.db.rollback()
                logger.error(f"MessageService: Error updating message ID {message_id}. DB Rollback. Error: {e}", exc_info=True)
                raise
        else:
            logger.info(f"MessageService: No changes applied to message ID {message_id}.")
            return db_message

    async def delete_message_by_id_logically(
        self,
        message_id: int,
        business_id: int
    ) -> bool:
        logger.info(f"MessageService: Attempting logical delete for message ID {message_id}, Business ID {business_id}.")
        db_message = await self.get_message_by_id_for_business(message_id, business_id)

        if not db_message:
            return False

        deleted_successfully = False
        try:
            if db_message.message_type == GlobalMessageTypeEnum.SCHEDULED_MESSAGE and \
               db_message.status == GlobalMessageStatusEnum.SCHEDULED:
                logger.info(f"MessageService: Soft deleting scheduled message ID {message_id}.")
                db_message.status = GlobalMessageStatusEnum.DELETED
                db_message.is_hidden = True
                db_message.updated_at = get_utc_now()
            else:
                logger.info(f"MessageService: Hard deleting message ID {message_id} (Type: {db_message.message_type}, Status: {db_message.status}).")
                await self.db.delete(db_message)

            await self.db.commit()
            deleted_successfully = True
            logger.info(f"MessageService: Message ID {message_id} processed for deletion (soft/hard).")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"MessageService: Error during deletion of message ID {message_id}. DB Rollback. Error: {e}", exc_info=True)
            raise
        
        return deleted_successfully

    async def _get_customer_consent_status(self, customer_id: int) -> str:
        stmt = (
            select(ConsentLog.status)
            .filter(ConsentLog.customer_id == customer_id)
            .order_by(ConsentLog.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        latest_consent_status_enum = result.scalars().first()

        if latest_consent_status_enum:
            return latest_consent_status_enum.value if isinstance(latest_consent_status_enum, Enum) else str(latest_consent_status_enum)
        return GlobalOptInStatus.NOT_SET.value

    def _format_scheduled_message(self, message: Message, customer: Customer) -> Dict:
        return {
            "id": message.id,
            "customer_name": customer.customer_name,
            "content": message.content,
            "scheduled_time": message.scheduled_send_at.isoformat() if message.scheduled_send_at else None,
            "status": message.status.value if isinstance(message.status, Enum) else str(message.status),
            "source": message.message_metadata.get('source', 'scheduled') if message.message_metadata else 'scheduled'
        }