# backend/app/models.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, UniqueConstraint, Index, JSON, func
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from app.database import Base
import datetime
import uuid
import json
import enum

# --- OptInStatus ENUM DEFINITION (YOUR EXISTING ENUM) ---
class OptInStatus(str, enum.Enum):
    PENDING = "pending"
    OPTED_IN = "opted_in"
    OPTED_OUT = "opted_out"
    NOT_SET = "not_set" # Or a suitable default

def utc_now(): # YOUR EXISTING FUNCTION
    return datetime.datetime.utcnow()

# --- START MODIFICATION: Define proper Enums ---
class MessageTypeEnum(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound" # A generic outbound message
    SCHEDULED = "scheduled" # A message scheduled by the system/user
    DRAFT = "draft" # A generic draft
    AI_DRAFT = "ai_draft" # Specifically an AI-generated draft for review
    OUTBOUND_AI_REPLY = "outbound_ai_reply" # An AI-generated reply sent directly
    INTERNAL_NOTIFICATION = "internal_notification" # For internal system notifications logged as messages

class MessageStatusEnum(str, enum.Enum):
    # For Message.status
    PENDING_REVIEW = "pending_review" # If a message itself needs review (less common for Message, more for Engagement)
    PENDING = "pending"          # Ready to be sent, awaiting processing by a sender (e.g., Twilio)
    SCHEDULED = "scheduled"      # Scheduled for future delivery
    QUEUED = "queued"            # Successfully handed off to a sending service like Twilio
    SENT = "sent"                # Confirmed sent by the provider (e.g., Twilio accepted it)
    DELIVERED = "delivered"      # Confirmed delivered to the handset by provider
    FAILED = "failed"            # Failed to send or deliver
    RECEIVED = "received"        # For inbound messages, successfully received
    DELETED = "deleted"          # If you allow soft deletion of messages
    FAILED_TO_SEND = "failed_to_send" # Explicit status for sending failures

    # For Engagement.status (some might overlap, some might be specific)
    # PENDING_REVIEW is already defined, good for Engagement
    AUTO_REPLIED_FAQ = "auto_replied_faq"
    PROCESSING_SEND = "processing_send" # For messages handed off to Celery/Twilio
    APPROVED = "approved"
    REJECTED_DRAFT = "rejected_draft" # if a draft is rejected by owner
    MANUALLY_SENT = "manually_sent" # if owner edits and sends a draft
    DRAFT = "draft"


class NudgeTypeEnum(str, enum.Enum):
    SENTIMENT_POSITIVE = "sentiment_positive"
    SENTIMENT_NEGATIVE = "sentiment_negative"
    POTENTIAL_TARGETED_EVENT = "potential_targeted_event" # AI detected a specific timed event opportunity
    STRATEGIC_ENGAGEMENT_OPPORTUNITY = "strategic_engagement_opportunity" # AI suggests a plan for nuanced replies or other events
    GOAL_OPPORTUNITY = "goal_opportunity"

class NudgeStatusEnum(str, enum.Enum):
    ACTIVE = "active"        # Nudge is new and actionable
    ACTIONED = "actioned"    # User took primary action on the nudge
    DISMISSED = "dismissed"  # User dismissed the nudge
    EXPIRED = "expired"      # Nudge is no longer relevant (optional, for future use)
    ERROR = "error"          # Error during nudge generation or processing
# --- END MODIFICATION: Define proper Enums ---


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
    updated_at = Column(DateTime, nullable=True, onupdate=utc_now) 

    notify_owner_on_reply_with_link = Column(Boolean, default=False, nullable=False)
    enable_ai_faq_auto_reply = Column(Boolean, default=False, nullable=False)
    structured_faq_data = Column(JSON, nullable=True)
    review_platform_url = Column(String, nullable=True)

    customers = relationship("Customer", back_populates="business", cascade="all, delete-orphan") 
    conversations = relationship("Conversation", back_populates="business", cascade="all, delete-orphan") 
    messages = relationship("Message", back_populates="business", cascade="all, delete-orphan") 
    engagements = relationship("Engagement", back_populates="business", cascade="all, delete-orphan") 
    roadmap_messages = relationship("RoadmapMessage", back_populates="business", cascade="all, delete-orphan") 
    scheduled_sms = relationship("ScheduledSMS", back_populates="business", cascade="all, delete-orphan") 
    consent_logs = relationship("ConsentLog", back_populates="business", cascade="all, delete-orphan") 
    co_pilot_nudges = relationship("CoPilotNudge", back_populates="business", cascade="all, delete-orphan")
    targeted_events = relationship("TargetedEvent", back_populates="business", cascade="all, delete-orphan")

    tags = relationship(
        "Tag",
        back_populates="business", 
        cascade="all, delete-orphan"
    )

class Customer(Base): 
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String)
    phone = Column(String)
    lifecycle_stage = Column(String)
    pain_points = Column(Text)
    interaction_history = Column(Text)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), index=True)
    timezone = Column(String, nullable=True)
    opted_in = Column(Boolean, default=False)
    sms_opt_in_status = Column(String, default=OptInStatus.NOT_SET.value, nullable=False)
    is_generating_roadmap = Column(Boolean, default=False)
    last_generation_attempt = Column(DateTime, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True, onupdate=utc_now) 
    last_read_at = Column(TIMESTAMP(timezone=True), nullable=True) # NEW: Add last_read_at

    business = relationship("BusinessProfile", back_populates="customers")
    conversations = relationship("Conversation", back_populates="customer", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="customer", cascade="all, delete-orphan")
    engagements = relationship("Engagement", back_populates="customer", cascade="all, delete-orphan")
    roadmap_messages = relationship("RoadmapMessage", back_populates="customer", cascade="all, delete-orphan")
    scheduled_sms = relationship("ScheduledSMS", back_populates="customer", cascade="all, delete-orphan")
    consent_logs = relationship("ConsentLog", back_populates="customer", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary="customer_tags", back_populates="customers")
    co_pilot_nudges = relationship("CoPilotNudge", back_populates="customer", cascade="all, delete-orphan")
    targeted_events = relationship("TargetedEvent", back_populates="customer", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("phone", "business_id", name="unique_customer_phone_per_business"),)


class Conversation(Base): 
    __tablename__ = "conversations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE")) 
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE")) 
    status = Column(String, default="active")
    started_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    last_message_at = Column(TIMESTAMP(timezone=True), default=utc_now)

    customer = relationship("Customer", back_populates="conversations")
    business = relationship("BusinessProfile", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    __table_args__ = (Index('idx_conversation_customer', 'customer_id'), Index('idx_conversation_business', 'business_id'), Index('idx_conversation_status', 'status'),)


class Message(Base): 
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE")) 
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="SET NULL"), nullable=True) 
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True) 
    content = Column(Text)
    message_type = Column(String, index=True, nullable=False, default=MessageTypeEnum.OUTBOUND.value) 
    status = Column(String, index=True, nullable=False, default=MessageStatusEnum.PENDING.value) 
    parent_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    scheduled_time = Column(TIMESTAMP(timezone=True), nullable=True)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    is_hidden = Column(Boolean, default=False)
    message_metadata = Column(JSON, nullable=True) 
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)

    conversation = relationship("Conversation", back_populates="messages")
    business = relationship("BusinessProfile", back_populates="messages")
    customer = relationship("Customer", back_populates="messages")
    parent = relationship("Message", remote_side=[id]) 
    __table_args__ = (Index('idx_message_conversation', 'conversation_id'), Index('idx_message_customer', 'customer_id'), Index('idx_message_business', 'business_id'), Index('idx_message_type', 'message_type'), Index('idx_message_status', 'status'), Index('idx_message_scheduled', 'scheduled_time'),)


class RoadmapMessage(Base): 
    __tablename__ = "roadmap_messages"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True) 
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE")) 
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE")) 
    smsContent = Column(Text)
    smsTiming = Column(Text)
    status = Column(String, default=MessageStatusEnum.PENDING_REVIEW.value)
    send_datetime_utc = Column(TIMESTAMP(timezone=True), nullable=True)
    relevance = Column(Text, nullable=True)
    success_indicator = Column(Text, nullable=True)
    no_response_plan = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True, onupdate=utc_now)

    message = relationship("Message") 
    customer = relationship("Customer", back_populates="roadmap_messages")
    business = relationship("BusinessProfile", back_populates="roadmap_messages")
    __table_args__ = (Index('idx_roadmap_customer', 'customer_id'), Index('idx_roadmap_business', 'business_id'), Index('idx_roadmap_status', 'status'),)
    @property
    def timing_dict(self):
        try: return json.loads(self.smsTiming)
        except: return {}


class Engagement(Base): 
    __tablename__ = "engagements"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True) 
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"))
    response = Column(Text, nullable=True) 
    ai_response = Column(Text, nullable=True) 
    status = Column(String, default=MessageStatusEnum.PENDING_REVIEW.value, nullable=False)
    parent_engagement_id = Column(Integer, ForeignKey("engagements.id"), nullable=True)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True, onupdate=utc_now)
    message_metadata = Column(JSON, nullable=True) 

    message = relationship("Message") 
    customer = relationship("Customer", back_populates="engagements")
    business = relationship("BusinessProfile", back_populates="engagements")
    parent_engagement = relationship("Engagement", remote_side=[id])
    __table_args__ = (Index('idx_engagement_customer', 'customer_id'), Index('idx_engagement_business', 'business_id'), Index('idx_engagement_status', 'status'), Index('idx_engagement_sent', 'sent_at'),)


class BusinessOwnerStyle(Base): 
    __tablename__ = "business_owner_styles"
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False) 
    scenario = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    context_type = Column(String, nullable=False)
    key_phrases = Column(JSON, nullable=True)
    style_notes = Column(JSON, nullable=True)
    personality_traits = Column(JSON, nullable=True)
    message_patterns = Column(JSON, nullable=True)
    special_elements = Column(JSON, nullable=True)
    last_analyzed = Column(TIMESTAMP(timezone=True), default=utc_now)
    business = relationship("BusinessProfile") 
    @property
    def style_guide(self):
        return {
            'key_phrases': json.loads(self.key_phrases) if self.key_phrases else [],
            'style_notes': json.loads(self.style_notes) if self.style_notes else {'tone': '', 'formality_level': '', 'personal_touches': [], 'authenticity_markers': []},
            'personality_traits': json.loads(self.personality_traits) if self.personality_traits else [],
            'message_patterns': json.loads(self.message_patterns) if self.message_patterns else {'greetings': [], 'closings': [], 'transitions': [], 'emphasis_patterns': []},
            'special_elements': json.loads(self.special_elements) if self.special_elements else {'industry_terms': [], 'metaphors': [], 'personal_references': [], 'emotional_markers': []}
        }

class ConsentLog(Base): 
    __tablename__ = "consent_log"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"))
    method = Column(String)
    phone_number = Column(String)
    message_sid = Column(String, nullable=True)
    status = Column(String, default="pending")
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True) 
    replied_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True, onupdate=utc_now)

    customer = relationship("Customer", back_populates="consent_logs")
    business = relationship("BusinessProfile", back_populates="consent_logs")


class ScheduledSMS(Base): 
    __tablename__ = "scheduled_sms"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"))
    message = Column(Text)
    status = Column(String, default=MessageStatusEnum.SCHEDULED.value)
    send_time = Column(DateTime) 
    source = Column(String, nullable=True)
    roadmap_id = Column(Integer, ForeignKey("roadmap_messages.id", ondelete="SET NULL"), nullable=True) 
    is_hidden = Column(Boolean, default=False)
    business_timezone = Column(String)
    customer_timezone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    customer = relationship("Customer", back_populates="scheduled_sms")
    business = relationship("BusinessProfile", back_populates="scheduled_sms")
    roadmap = relationship("RoadmapMessage") 


class Tag(Base): 
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    business = relationship(
        "BusinessProfile",
        back_populates="tags" 
    )
    customers = relationship(
        "Customer",
        secondary="customer_tags",
        back_populates="tags" 
    )
    __table_args__ = (UniqueConstraint('business_id', 'name', name='uq_tag_name_per_business'), Index('idx_tag_business_name', 'business_id', 'name'),)


class CustomerTag(Base): 
    __tablename__ = "customer_tags"
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

class CoPilotNudge(Base):
    __tablename__ = "co_pilot_nudges"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True)

    nudge_type = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False, default=NudgeStatusEnum.ACTIVE.value)

    message_snippet = Column(Text, nullable=True)
    ai_suggestion = Column(Text, nullable=True)
    
    ai_evidence_snippet = Column(JSON, nullable=True) 
    ai_suggestion_payload = Column(JSON, nullable=True) 

    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), default=utc_now, onupdate=utc_now)
    
    business = relationship("BusinessProfile", back_populates="co_pilot_nudges")
    customer = relationship("Customer", back_populates="co_pilot_nudges")
    created_targeted_event = relationship("TargetedEvent", back_populates="nudge", uselist=False)

    __table_args__ = (
        Index('idx_copilotnudge_business_type_status', 'business_id', 'nudge_type', 'status'),
    )

    def __repr__(self):
        return f"<CoPilotNudge(id={self.id}, type='{self.nudge_type}', status='{self.status}', business_id={self.business_id})>"

class TargetedEvent(Base):
    __tablename__ = "targeted_events"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)

    event_datetime_utc = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    purpose = Column(Text, nullable=True)

    status = Column(String, default="AI_Suggested", nullable=False, index=True) 

    notes = Column(Text, nullable=True)

    created_from_nudge_id = Column(Integer, ForeignKey("co_pilot_nudges.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), default=utc_now, onupdate=utc_now)

    business = relationship("BusinessProfile", back_populates="targeted_events")
    customer = relationship("Customer", back_populates="targeted_events")
    nudge = relationship("CoPilotNudge", back_populates="created_targeted_event")

    __table_args__ = (
        Index('idx_targetevent_biz_cust_dt', 'business_id', 'customer_id', 'event_datetime_utc'),
    )

    def __repr__(self):
        return f"<TargetedEvent(id={self.id}, customer_id={self.customer_id}, datetime='{self.event_datetime_utc}', status='{self.status}')>"