from enum import Enum
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models import Message, RoadmapMessage, Customer, ConsentLog, Conversation, BusinessProfile
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
        roadmap_query = self.db.query(RoadmapMessage).filter(
            and_(
                RoadmapMessage.customer_id == customer_id,
                RoadmapMessage.send_datetime_utc != None,
                RoadmapMessage.status != MessageStatus.DELETED.value
            )
        )
        
        # Base query for scheduled messages
        scheduled_query = self.db.query(Message).filter(
            Message.customer_id == customer_id,
            Message.message_type == 'scheduled'
        )
        
        if not include_past:
            roadmap_query = roadmap_query.filter(RoadmapMessage.send_datetime_utc >= now_utc)
            scheduled_query = scheduled_query.filter(Message.scheduled_time >= now_utc)
            
        return {
            "roadmap": roadmap_query.all(),
            "scheduled": scheduled_query.all(),
            "consent_status": self._get_customer_consent_status(customer_id)
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

    def _get_customer_consent_status(self, customer_id: int) -> str:
        """Get latest consent status for a customer"""
        latest_consent = (
            self.db.query(ConsentLog)
            .filter(ConsentLog.customer_id == customer_id)
            .order_by(ConsentLog.replied_at.desc())
            .first()
        )
        return latest_consent.status if latest_consent else "pending"
        
    def _format_scheduled_message(self, message: Message, customer: Customer) -> Dict:
        """Format scheduled message for API response"""
        return {
            "id": message.id,
            "customer_name": customer.customer_name,
            "content": message.content,
            "scheduled_time": message.scheduled_time.isoformat() if message.scheduled_time else None,
            "status": message.status,
            "source": message.metadata.get('source', 'scheduled') if message.metadata else 'scheduled'
        } 