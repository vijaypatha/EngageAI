from enum import Enum
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, desc # Added desc
from app.models import Message, RoadmapMessage, Customer, ConsentLog, Conversation, BusinessProfile, OptInStatus # Added OptInStatus
import logging
import uuid

logger = logging.getLogger(__name__)

class MessageStatus(Enum):
    PENDING = "pending_review"
    SCHEDULED = "scheduled"
    SENT = "sent"
    REJECTED = "rejected"
    DELETED = "deleted"

class MessageService:
    def __init__(self, db: Session):
        self.db = db
        
    def get_customer_messages(
        self, 
        customer_id: int, 
        include_past: bool = False
    ) -> Dict:
        """Get all messages for a customer with proper status handling"""
        now_utc = datetime.now(timezone.utc)
        
        # Base query for roadmap messages
        roadmap_query = (
            self.db.query(RoadmapMessage)
            .options(
                joinedload(RoadmapMessage.customer),
                joinedload(RoadmapMessage.business),
                joinedload(RoadmapMessage.message), # Eager load related Message
            )
            .filter(
                and_(
                    RoadmapMessage.customer_id == customer_id,
                    RoadmapMessage.send_datetime_utc != None,
                    RoadmapMessage.status != MessageStatus.DELETED.value,
                )
            )
        )

        # Base query for scheduled messages
        scheduled_query = (
            self.db.query(Message)
            .options(
                joinedload(Message.customer),
                joinedload(Message.business),
                joinedload(Message.conversation), # Eager load related Conversation
            )
            .filter(
                Message.customer_id == customer_id, Message.message_type == "scheduled"
            )
        )

        if not include_past:
            roadmap_query = roadmap_query.filter(
                RoadmapMessage.send_datetime_utc >= now_utc
            )
            scheduled_query = scheduled_query.filter(Message.scheduled_time >= now_utc)

        # Get customer - we might still need the customer object for other info or fallback.
        # If only opted_in is needed as fallback, we can remove joinedload for consent_logs.
        customer = (
            self.db.query(Customer)
            # .options(joinedload(Customer.consent_logs)) # Removing this if logs are not used elsewhere in this func
            .filter(Customer.id == customer_id)
            .first()
        )

        # More efficient query for the latest consent log
        latest_consent_log_entry = (
            self.db.query(ConsentLog)
            .filter(ConsentLog.customer_id == customer_id)
            .order_by(desc(ConsentLog.replied_at)) # Order by replied_at descending
            .first()
        )

        consent_status = "pending" # Default
        if latest_consent_log_entry:
            consent_status = latest_consent_log_entry.status
        elif customer and customer.opted_in: # Fallback if no consent logs but customer exists and opted_in is true
            consent_status = OptInStatus.OPTED_IN.value # Ensure OptInStatus is imported from app.models


        return {
            "roadmap": roadmap_query.all(),
            "scheduled": scheduled_query.all(),
            "consent_status": consent_status,
        }

    def schedule_message(
        self,
        customer_id: int,
        business_id: int,
        content: str,
        scheduled_time: datetime = None
    ) -> Message:
        """Schedule a new message"""
        # First check if customer has opted in
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer or not customer.opted_in:
            raise ValueError("Customer has not opted in to receive SMS")

        # Create the message
        message = self.create_message(
            customer_id=customer_id,
            business_id=business_id,
            content=content,
            scheduled_time=scheduled_time,
            message_type="scheduled"
        )

        # The actual scheduling will be handled by the celery beat scheduler
        return message

    def create_message(
        self,
        customer_id: int,
        business_id: int,
        content: str,
        scheduled_time: datetime = None,
        message_type: str = "scheduled"
    ) -> Message:
        """Create a new message"""
        message = Message(
            customer_id=customer_id,
            business_id=business_id,
            content=content,
            scheduled_time=scheduled_time or datetime.utcnow(),
            message_type=message_type,
            status="scheduled"
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def get_message(self, message_id: int) -> Message:
        """Get a message by ID"""
        return self.db.query(Message).filter(Message.id == message_id).first()

    def update_message_status(self, message_id: int, status: str) -> Message:
        """Update message status"""
        message = self.get_message(message_id)
        if message:
            message.status = status
            if status == "sent":
                message.sent_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(message)
        return message

    # This function is now integrated into get_customer_messages
    # def _get_customer_consent_status(self, customer_id: int) -> str:
    #     """Get latest consent status for a customer"""
    #     latest_consent = (
    #         self.db.query(ConsentLog)
    #         .filter(ConsentLog.customer_id == customer_id)
    #         .order_by(ConsentLog.replied_at.desc())
    #         .first()
    #     )
    #     return latest_consent.status if latest_consent else "pending"

    def _format_scheduled_message(self, message: Message, customer: Customer) -> Dict:
        """Format scheduled message for API response"""
        return {
            "id": message.id,
            "customer_name": customer.customer_name,
            "content": message.content,
            "scheduled_time": message.scheduled_time.isoformat() if message.scheduled_time else None,
            "status": message.status,
            "source": message.message_metadata.get('source', 'scheduled') if message.message_metadata else 'scheduled'
        }

    def get_full_conversation_for_customer(self, customer_id: int) -> List[Message]:
        """
        Fetches all messages for a customer's conversation timeline, ordered by creation time.
        This includes messages sent by the business/AI and messages received from the customer.
        It aims to provide a base list of messages; the frontend will parse content as needed.
        """
        logger.info(f"Fetching full conversation for customer_id: {customer_id}")

        # Fetch all types of messages related to the customer.
        # This includes:
        # 1. Messages directly sent or scheduled (from Message table, message_type='direct', 'scheduled', 'outbound_ai_reply')
        # 2. Customer replies (often stored as 'response' in Engagement table, or could be Message with type='received')
        # 3. AI drafts (from Engagement table, status='pending_review', or Message with type='ai_draft')

        # For simplicity and to align with how `review.py/get_full_customer_history` constructs history,
        # we will query the `Message` table. The `Engagement` table entries that represent
        # customer replies or AI drafts that *don't* also have a corresponding `Message` table entry
        # would require more complex joining or unioning here.
        # The current `Message` model seems to be the primary store for sent/scheduled messages.
        # Customer replies are typically in `Engagement.response`.
        # AI Drafts are in `Engagement.ai_response` with status `pending_review`.

        # This query will fetch all Message entities linked to the customer.
        # The frontend's `TimelineEntry` processing logic will then need to correctly interpret
        # the `content` (which can be JSON string for AI messages) and `message_type`.

        # A more comprehensive solution might involve a UNION of different message sources (Message table, Engagement responses)
        # or ensuring all communications are consistently logged into the Message table with appropriate types.
        # For now, let's get all from Message table for this customer.
        # The frontend already has logic to interpret different message types and content structures.

        messages = (
            self.db.query(Message)
            .filter(Message.customer_id == customer_id)
            .order_by(Message.created_at.asc()) # Order by creation time for timeline
            .all()
        )

        # If customer replies or certain AI drafts are solely in the Engagement table and not mirrored
        # in the Message table, they would be missed by this query.
        # The `/review/full-customer-history` endpoint has a more complex assembly logic for this,
        # which might be too heavy for this specific service method if it's intended to be simpler.
        # However, to match the frontend's expectation of a full timeline, we might need to replicate
        # some of that assembly here or ensure all relevant events are in `Message`.

        # For now, returning what's in the Message table.
        # The frontend will need to be robust in handling these.
        # If `ConversationMessageForTimeline` schema requires specific fields not directly on `Message`
        # (e.g. a 'direction' field), those would need to be constructed/mapped here.
        # Our `ConversationMessageForTimeline` currently inherits directly from `Message`.

        logger.info(f"Found {len(messages)} messages in Message table for customer_id: {customer_id}")
        return messages