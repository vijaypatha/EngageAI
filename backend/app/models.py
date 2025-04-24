from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, UniqueConstraint, Index, JSON
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import datetime
from datetime import timezone
import uuid
import json

class MessageStatus:
    PENDING = "pending_review"
    SCHEDULED = "scheduled"
    SENT = "sent"
    DELETED = "deleted"

class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id = Column(Integer, primary_key=True)
    business_name = Column(String, unique=True, index=True)
    slug = Column(String, unique=True, index=True)
    industry = Column(String)
    business_goal = Column(String, nullable=True)
    primary_services = Column(String, nullable=True)
    representative_name = Column(String, nullable=True)
    twilio_number = Column(String, nullable=True)
    timezone = Column(String, default="UTC")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(timezone.utc), onupdate=lambda: datetime.datetime.now(timezone.utc))

    # Relationships
    customers = relationship("Customer", back_populates="business")
    messages = relationship("Message", back_populates="business")
    roadmap_messages = relationship("RoadmapMessage", back_populates="business")
    engagements = relationship("Engagement", back_populates="business")

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    customer_name = Column(String, index=True)
    phone = Column(String, index=True)
    lifecycle_stage = Column(String, nullable=True)
    pain_points = Column(Text, nullable=True)
    interaction_history = Column(Text, nullable=True)
    timezone = Column(String, nullable=True)
    opted_in = Column(Boolean, nullable=True)
    is_generating_roadmap = Column(Boolean, default=False)
    last_generation_attempt = Column(DateTime, nullable=True)  # No timezone needed - internal tracking
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(timezone.utc), onupdate=lambda: datetime.datetime.now(timezone.utc))

    # Relationships
    business = relationship("BusinessProfile", back_populates="customers")
    messages = relationship("Message", back_populates="customer")
    roadmap_messages = relationship("RoadmapMessage", back_populates="customer")
    engagements = relationship("Engagement", back_populates="customer")
    conversations = relationship("Conversation", back_populates="customer")

    __table_args__ = (
        UniqueConstraint("phone", "business_id", name="unique_customer_phone_per_business"),
    )

class Conversation(Base):
    """Tracks message threads between business and customer"""
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    started_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))
    last_message_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))
    status = Column(String, default="active")  # active, archived, deleted

    # Relationships
    customer = relationship("Customer", back_populates="conversations")
    business = relationship("BusinessProfile")
    messages = relationship("Message", back_populates="conversation")

    __table_args__ = (
        Index('idx_conversation_customer', 'customer_id'),
        Index('idx_conversation_business', 'business_id'),
        Index('idx_conversation_status', 'status'),
    )

class Message(Base):
    """Base class for all messages"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(String, nullable=False)  # 'roadmap', 'scheduled', 'response', 'ai_response'
    status = Column(String, nullable=False, default='pending_review')  # pending_review, scheduled, sent, deleted
    parent_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    is_hidden = Column(Boolean, default=False)
    message_metadata = Column(JSON, nullable=True)  # Renamed from metadata to message_metadata
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(timezone.utc))

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    business = relationship("BusinessProfile", back_populates="messages")
    customer = relationship("Customer", back_populates="messages")
    replies = relationship("Message", backref=backref("parent", remote_side=[id]))

    __table_args__ = (
        Index('idx_message_conversation', 'conversation_id'),
        Index('idx_message_customer', 'customer_id'),
        Index('idx_message_business', 'business_id'),
        Index('idx_message_type', 'message_type'),
        Index('idx_message_status', 'status'),
        Index('idx_message_scheduled', 'scheduled_time'),
    )

class RoadmapMessage(Base):
    __tablename__ = "roadmap_messages"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    smsContent = Column(Text, nullable=False)
    smsTiming = Column(Text, nullable=False)  # JSON string
    status = Column(String, default=MessageStatus.PENDING)
    send_datetime_utc = Column(DateTime, nullable=True)
    relevance = Column(Text, nullable=True)
    success_indicator = Column(Text, nullable=True)
    no_response_plan = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc), onupdate=lambda: datetime.datetime.now(timezone.utc))

    # Relationships
    message = relationship("Message", backref="roadmap_message", uselist=False)
    customer = relationship("Customer", back_populates="roadmap_messages")
    business = relationship("BusinessProfile", back_populates="roadmap_messages")
    scheduled_message = relationship("Message", back_populates="roadmap_message", uselist=False, overlaps="message")

    __table_args__ = (
        Index('idx_roadmap_customer', 'customer_id'),
        Index('idx_roadmap_business', 'business_id'),
        Index('idx_roadmap_status', 'status'),
    )

    @property
    def timing_dict(self):
        try:
            return json.loads(self.smsTiming)
        except:
            return {}

class Engagement(Base):
    __tablename__ = "engagements"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    response = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=True)
    status = Column(String, default=MessageStatus.PENDING)
    parent_engagement_id = Column(Integer, ForeignKey("engagements.id"), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc), onupdate=lambda: datetime.datetime.now(timezone.utc))

    # Relationships
    message = relationship("Message", backref="engagement", uselist=False)
    customer = relationship("Customer", back_populates="engagements")
    business = relationship("BusinessProfile", back_populates="engagements")
    parent_engagement = relationship("Engagement", remote_side=[id], backref="replies")

    __table_args__ = (
        Index('idx_engagement_customer', 'customer_id'),
        Index('idx_engagement_business', 'business_id'),
        Index('idx_engagement_status', 'status'),
        Index('idx_engagement_sent', 'sent_at'),
    )

class BusinessOwnerStyle(Base):
    __tablename__ = "business_owner_styles"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    scenario = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    context_type = Column(String, nullable=False)
    key_phrases = Column(JSON, nullable=True)
    style_notes = Column(JSON, nullable=True)
    personality_traits = Column(JSON, nullable=True)
    message_patterns = Column(JSON, nullable=True)
    special_elements = Column(JSON, nullable=True)
    last_analyzed = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(timezone.utc))
    business = relationship("BusinessProfile")

    @property
    def style_guide(self):
        """Returns complete style guide as a dictionary"""
        return {
            'key_phrases': json.loads(self.key_phrases) if self.key_phrases else [],
            'style_notes': json.loads(self.style_notes) if self.style_notes else {},
            'personality_traits': json.loads(self.personality_traits) if self.personality_traits else [],
            'message_patterns': json.loads(self.message_patterns) if self.message_patterns else [],
            'special_elements': json.loads(self.special_elements) if self.special_elements else {}
        }

class ConsentLog(Base):
    __tablename__ = "consent_log"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    method = Column(String, nullable=False)  # e.g., "double_opt_in"
    phone_number = Column(String, nullable=False)
    message_sid = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, opted_in, declined, stopped
    sent_at = Column(DateTime(timezone=True), nullable=False)
    replied_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('idx_consent_customer_replied', 'customer_id', 'replied_at'),
    )