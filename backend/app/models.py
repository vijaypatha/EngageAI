from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, UniqueConstraint, Index, JSON, func
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from app.database import Base
import datetime
import uuid
import json

def utc_now():
    return datetime.datetime.utcnow()

class MessageStatus:
    PENDING = "pending_review"
    SCHEDULED = "scheduled"
    SENT = "sent"
    DELETED = "deleted"

class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String, unique=True, index=True)
    industry = Column(String)
    business_goal = Column(String)
    primary_services = Column(String)
    representative_name = Column(String)
    timezone = Column(String, default="UTC")
    twilio_number = Column(String, nullable=True)
    twilio_sid = Column(String, nullable=True)
    messaging_service_sid = Column(String, nullable=True)
    business_phone_number = Column(String, nullable=True)
    slug = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, nullable=True)

    # Relationships
    customers = relationship("Customer", back_populates="business")
    conversations = relationship("Conversation", back_populates="business")
    messages = relationship("Message", back_populates="business")
    engagements = relationship("Engagement", back_populates="business")
    roadmap_messages = relationship("RoadmapMessage", back_populates="business")
    scheduled_sms = relationship("ScheduledSMS", back_populates="business")
    consent_logs = relationship("ConsentLog", back_populates="business")
    tags = relationship("Tag", backref="business", cascade="all, delete-orphan")

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String)
    phone = Column(String)
    lifecycle_stage = Column(String)
    pain_points = Column(Text)
    interaction_history = Column(Text)
    business_id = Column(Integer, ForeignKey("business_profiles.id"))
    timezone = Column(String, nullable=True)
    opted_in = Column(Boolean, default=False)
    is_generating_roadmap = Column(Boolean, default=False)
    last_generation_attempt = Column(DateTime, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    business = relationship("BusinessProfile", back_populates="customers")
    conversations = relationship("Conversation", back_populates="customer")
    messages = relationship("Message", back_populates="customer")
    engagements = relationship("Engagement", back_populates="customer")
    roadmap_messages = relationship("RoadmapMessage", back_populates="customer")
    scheduled_sms = relationship("ScheduledSMS", back_populates="customer")
    consent_logs = relationship("ConsentLog", back_populates="customer")
    tags = relationship("Tag", secondary="customer_tags", backref="customers") # Use backref for simplicity here


    __table_args__ = (
        UniqueConstraint("phone", "business_id", name="unique_customer_phone_per_business"),
    )

class Conversation(Base):
    """Tracks message threads between business and customer"""
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    business_id = Column(Integer, ForeignKey("business_profiles.id"))
    status = Column(String, default="active")
    started_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    last_message_at = Column(TIMESTAMP(timezone=True), default=utc_now)

    # Relationships
    customer = relationship("Customer", back_populates="conversations")
    business = relationship("BusinessProfile", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")

    __table_args__ = (
        Index('idx_conversation_customer', 'customer_id'),
        Index('idx_conversation_business', 'business_id'),
        Index('idx_conversation_status', 'status'),
    )

class Message(Base):
    """Base class for all messages"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"))
    business_id = Column(Integer, ForeignKey("business_profiles.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    content = Column(Text)
    message_type = Column(String)
    status = Column(String, default="pending_review")
    parent_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    scheduled_time = Column(TIMESTAMP(timezone=True), nullable=True)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    is_hidden = Column(Boolean, default=False)
    message_metadata = Column(JSON, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    business = relationship("BusinessProfile", back_populates="messages")
    customer = relationship("Customer", back_populates="messages")
    parent = relationship("Message", remote_side=[id])

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
    message_id = Column(Integer, ForeignKey("messages.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    business_id = Column(Integer, ForeignKey("business_profiles.id"))
    smsContent = Column(Text)
    smsTiming = Column(Text)
    status = Column(String, default="pending_review")
    send_datetime_utc = Column(TIMESTAMP(timezone=True), nullable=True)
    relevance = Column(Text, nullable=True)
    success_indicator = Column(Text, nullable=True)
    no_response_plan = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    message = relationship("Message")
    customer = relationship("Customer", back_populates="roadmap_messages")
    business = relationship("BusinessProfile", back_populates="roadmap_messages")

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
    message_id = Column(Integer, ForeignKey("messages.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    business_id = Column(Integer, ForeignKey("business_profiles.id"))
    response = Column(Text)
    ai_response = Column(Text, nullable=True)
    status = Column(String, default="pending_review")
    parent_engagement_id = Column(Integer, ForeignKey("engagements.id"), nullable=True)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True)
    message_metadata = Column(JSON, nullable=True)

    # Relationships
    message = relationship("Message")
    customer = relationship("Customer", back_populates="engagements")
    business = relationship("BusinessProfile", back_populates="engagements")
    parent_engagement = relationship("Engagement", remote_side=[id])

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
    response = Column(Text, nullable=False)  # The business owner's authentic response
    context_type = Column(String, nullable=False)  # Type of interaction (inquiry, follow-up, etc.)
    key_phrases = Column(JSON, nullable=True)  # Signature phrases and expressions they use
    style_notes = Column(JSON, nullable=True)  # Overall tone, formality level, and unique style markers
    personality_traits = Column(JSON, nullable=True)  # Personality reflected in their writing
    message_patterns = Column(JSON, nullable=True)  # How they structure their messages
    special_elements = Column(JSON, nullable=True)  # Industry terms, metaphors, personal touches
    last_analyzed = Column(TIMESTAMP(timezone=True), default=utc_now)
    business = relationship("BusinessProfile")

    @property
    def style_guide(self):
        """Returns complete style guide as a dictionary"""
        return {
            'key_phrases': json.loads(self.key_phrases) if self.key_phrases else [],
            'style_notes': json.loads(self.style_notes) if self.style_notes else {
                'tone': '',  # warm, professional, casual, etc.
                'formality_level': '',  # formal, semi-formal, casual
                'personal_touches': [],  # ways they make messages personal
                'authenticity_markers': []  # what makes their voice genuine
            },
            'personality_traits': json.loads(self.personality_traits) if self.personality_traits else [],
            'message_patterns': json.loads(self.message_patterns) if self.message_patterns else {
                'greetings': [],  # how they start messages
                'closings': [],  # how they end messages
                'transitions': [],  # how they connect ideas
                'emphasis_patterns': []  # how they emphasize important points
            },
            'special_elements': json.loads(self.special_elements) if self.special_elements else {
                'industry_terms': [],  # professional vocabulary
                'metaphors': [],  # common comparisons they use
                'personal_references': [],  # how they reference themselves/their business
                'emotional_markers': []  # how they express empathy/understanding
            }
        }

class ConsentLog(Base):
    __tablename__ = "consent_log"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    business_id = Column(Integer, ForeignKey("business_profiles.id"))
    method = Column(String)
    phone_number = Column(String)
    message_sid = Column(String, nullable=True)
    status = Column(String, default="pending")
    sent_at = Column(TIMESTAMP(timezone=True))
    replied_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    customer = relationship("Customer", back_populates="consent_logs")
    business = relationship("BusinessProfile", back_populates="consent_logs")

class ScheduledSMS(Base):
    __tablename__ = "scheduled_sms"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    business_id = Column(Integer, ForeignKey("business_profiles.id"))
    message = Column(Text)
    status = Column(String, default="scheduled")
    send_time = Column(DateTime)
    source = Column(String, nullable=True)
    roadmap_id = Column(Integer, ForeignKey("roadmap_messages.id"), nullable=True)
    is_hidden = Column(Boolean, default=False)
    business_timezone = Column(String)
    customer_timezone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)

    # Relationships
    customer = relationship("Customer", back_populates="scheduled_sms")
    business = relationship("BusinessProfile", back_populates="scheduled_sms")
    roadmap = relationship("RoadmapMessage")

class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, index=True)
    # Link to business, ensure deletion of business cascades here if desired
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True) # Stored lowercase, added length

    # Relationship to BusinessProfile defined below in BusinessProfile class using back_populates
    # (This avoids needing a backref definition here)

    # Ensure tag names are unique within a single business
    __table_args__ = (
        UniqueConstraint('business_id', 'name', name='uq_tag_name_per_business'),
        Index('idx_tag_business_name', 'business_id', 'name'),
    )

class CustomerTag(Base):
    __tablename__ = "customer_tags"
    # Define foreign keys first
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    # No extra relationships needed here; access happens via the 'secondary' link