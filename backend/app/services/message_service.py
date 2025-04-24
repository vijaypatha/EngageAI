from enum import Enum
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models import Message, RoadmapMessage, Customer, ConsentLog, Conversation
from app.celery_tasks import schedule_sms_task
import uuid

class MessageStatus(Enum):
    PENDING = "pending_review"
    SCHEDULED = "scheduled"
    SENT = "sent"
    REJECTED = "rejected"
    DELETED = "deleted"

class MessageService:
    def __init__(self, db: Session):
        self._db = db
        
    def get_customer_messages(
        self, 
        customer_id: int, 
        include_past: bool = False
    ) -> Dict:
        """Get all messages for a customer with proper status handling"""
        now_utc = datetime.now(timezone.utc)
        
        # Base query for roadmap messages
        roadmap_query = self._db.query(RoadmapMessage).filter(
            and_(
                RoadmapMessage.customer_id == customer_id,
                RoadmapMessage.send_datetime_utc != None,
                RoadmapMessage.status != MessageStatus.DELETED.value
            )
        )
        
        # Base query for scheduled messages
        scheduled_query = self._db.query(Message).filter(
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
        
    def schedule_message(self, roadmap_id: int) -> Dict:
        """Schedule a roadmap message with proper error handling and status sync"""
        roadmap_msg = self._db.query(RoadmapMessage).filter(RoadmapMessage.id == roadmap_id).first()
        if not roadmap_msg:
            raise ValueError("Roadmap message not found")
            
        if not roadmap_msg.send_datetime_utc:
            raise ValueError("Missing send time for roadmap message")
            
        if roadmap_msg.status == MessageStatus.SCHEDULED.value:
            return {"status": "already scheduled"}
            
        customer = self._db.query(Customer).filter(Customer.id == roadmap_msg.customer_id).first()
        if not customer or not customer.opted_in:
            raise ValueError("Customer has not opted in to receive SMS")
            
        # Get or create conversation
        conversation = self._db.query(Conversation).filter(
            Conversation.customer_id == customer.id,
            Conversation.business_id == roadmap_msg.business_id,
            Conversation.status == 'active'
        ).first()
        
        if not conversation:
            conversation = Conversation(
                id=uuid.uuid4(),
                customer_id=customer.id,
                business_id=roadmap_msg.business_id,
                started_at=datetime.now(timezone.utc),
                last_message_at=datetime.now(timezone.utc),
                status='active'
            )
            self._db.add(conversation)
            self._db.flush()

        # Create scheduled message
        message = Message(
            conversation_id=conversation.id,
            customer_id=roadmap_msg.customer_id,
            business_id=roadmap_msg.business_id,
            content=roadmap_msg.smsContent,
            message_type='scheduled',
            scheduled_time=roadmap_msg.send_datetime_utc,
            status=MessageStatus.SCHEDULED.value,
            metadata={
                'roadmap_id': roadmap_msg.id,
                'source': 'roadmap'
            }
        )
        
        try:
            self._db.add(message)
            roadmap_msg.status = MessageStatus.SCHEDULED.value
            self._db.commit()
            
            # Schedule Celery task
            schedule_sms_task.apply_async(args=[message.id], eta=roadmap_msg.send_datetime_utc)
            
            return {
                "status": "scheduled",
                "message_id": message.id,
                "details": self._format_scheduled_message(message, customer)
            }
        except Exception as e:
            self._db.rollback()
            raise ValueError(f"Failed to schedule message: {str(e)}")
            
    def _get_customer_consent_status(self, customer_id: int) -> str:
        """Get latest consent status for a customer"""
        latest_consent = (
            self._db.query(ConsentLog)
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