# backend/app/models.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, UniqueConstraint, Index, JSON, func, Enum as SAEnum, Time
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base
import datetime # Corrected from datetime to datetime for module access
import uuid # Corrected from uuid to uuid
import json # Added for json.loads
import enum
from typing import List


# --- OptInStatus ENUM DEFINITION ---
class OptInStatus(str, enum.Enum):
    PENDING = "pending"
    OPTED_IN = "opted_in"
    OPTED_OUT = "opted_out"
    NOT_SET = "not_set"
    PENDING_CONFIRMATION = "pending_confirmation"

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc) # Use datetime.datetime

# --- Enums (Python-side definitions) ---
class MessageTypeEnum(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    SCHEDULED_MESSAGE = "scheduled_message" # For explicit scheduled messages
    DRAFT = "draft"
    AI_DRAFT = "ai_draft"
    OUTBOUND_AI_REPLY = "outbound_ai_reply"
    SYSTEM = "system"
    APPOINTMENT_PROPOSAL = "appointment_proposal"
    APPOINTMENT_CONFIRMATION = "appointment_confirmation"
    APPOINTMENT_RESCHEDULE_SUGGESTION = "appointment_reschedule_suggestion"
    APPOINTMENT_CANCELLATION_NOTICE = "appointment_cancellation_notice"
    APPOINTMENT_REMINDER = "appointment_reminder" # Added for Celery task output
    APPOINTMENT_THANK_YOU = "appointment_thank_you" # Added for Celery task output

class MessageStatusEnum(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    PENDING = "pending" # General pending state
    PENDING_SEND = "pending_send" # Ready to be sent by a worker
    SCHEDULED = "scheduled" # Scheduled for future delivery
    QUEUED = "queued" # Sent to Twilio, waiting for their processing
    SENT = "sent" # Confirmed sent by Twilio
    DELIVERED = "delivered" # Confirmed delivered by Twilio carrier
    FAILED = "failed" # Failed to send
    RECEIVED = "received" # For inbound messages
    DELETED = "deleted" # Soft deleted, e.g., a cancelled scheduled message
    AUTO_REPLIED_FAQ = "auto_replied_faq"
    APPROVED = "approved" # e.g. an approved AI draft
    REJECTED_DRAFT = "rejected_draft"
    MANUALLY_SENT = "manually_sent"
    DRAFT = "draft" # General draft status

class AppointmentRequestStatusEnum(str, enum.Enum):
    PENDING_OWNER_ACTION = "pending_owner_action"
    BUSINESS_INITIATED_PENDING_CUSTOMER_REPLY = "business_initiated_pending_customer_reply"
    CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL = "customer_confirmed_pending_owner_approval"
    CUSTOMER_REQUESTED_RESCHEDULE = "customer_requested_reschedule"
    CUSTOMER_DECLINED_PROPOSAL = "customer_declined_proposal" # New
    CONFIRMED_BY_OWNER = "confirmed_by_owner"
    OWNER_PROPOSED_RESCHEDULE = "owner_proposed_reschedule"
    DECLINED_BY_OWNER = "declined_by_owner"
    CANCELLED_BY_OWNER = "cancelled_by_owner" # New, distinct from declined
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED_BY_CUSTOMER = "cancelled_by_customer" # New

class AppointmentRequestSourceEnum(str, enum.Enum):
    CUSTOMER_INITIATED = "customer_initiated"
    BUSINESS_INITIATED = "business_initiated"

class SenderTypeEnum(str, enum.Enum):
    BUSINESS = "business"
    CUSTOMER = "customer"
    SYSTEM = "system"

# Helper for SAEnum when native_enum=False to ensure Python enum values are used
def enum_values_callable(enum_class_passed_in):
    return [member.value for member in enum_class_passed_in]

# --- BusinessProfile Model ---
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
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=utc_now)
    notify_owner_on_reply_with_link = Column(Boolean, default=False, nullable=False)
    enable_ai_faq_auto_reply = Column(Boolean, default=False, nullable=False)
    structured_faq_data = Column(JSON, nullable=True) # Using generic JSON for broader compatibility if JSONB not available
    default_appointment_duration_minutes = Column(Integer, default=15, nullable=False)

    # New fields for Availability Settings
    availability_style = Column(String, nullable=True, default="smart_hours")
    smart_hours_config = Column(JSONB, nullable=True) # Using JSONB for PostgreSQL, fallback to JSON if needed
    manual_rules = Column(JSONB, nullable=True)       # Using JSONB for PostgreSQL, fallback to JSON if needed


    customers = relationship("Customer", back_populates="business", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="business", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="business", cascade="all, delete-orphan")
    engagements = relationship("Engagement", back_populates="business", cascade="all, delete-orphan")
    roadmap_messages = relationship("RoadmapMessage", back_populates="business", cascade="all, delete-orphan")
    consent_logs = relationship("ConsentLog", back_populates="business", cascade="all, delete-orphan")
    appointment_availabilities = relationship("AppointmentAvailability", back_populates="business", cascade="all, delete-orphan")
    appointment_requests = relationship("AppointmentRequest", back_populates="business", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="business", cascade="all, delete-orphan")


# --- Customer Model ---
class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, nullable=True)
    phone = Column(String, nullable=False, index=True)
    lifecycle_stage = Column(String, nullable=True)
    pain_points = Column(Text, nullable=True)
    interaction_history = Column(Text, nullable=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False)
    timezone = Column(String, nullable=True)
    opted_in = Column(Boolean, default=False)
    sms_opt_in_status = Column(
        SAEnum(
            OptInStatus,
            name="opt_in_status_enum",
            native_enum=False,
            values_callable=enum_values_callable,
            create_constraint=True
        ),
        default=OptInStatus.NOT_SET,
        nullable=False
    )
    is_generating_roadmap = Column(Boolean, default=False)
    last_generation_attempt = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    business = relationship("BusinessProfile", back_populates="customers")
    conversations = relationship("Conversation", back_populates="customer", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="customer", cascade="all, delete-orphan")
    engagements = relationship("Engagement", back_populates="customer", cascade="all, delete-orphan")
    roadmap_messages = relationship("RoadmapMessage", back_populates="customer", cascade="all, delete-orphan")
    consent_logs = relationship("ConsentLog", back_populates="customer", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary="customer_tags", back_populates="customers")
    appointment_requests = relationship("AppointmentRequest", back_populates="customer", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("phone", "business_id", name="uq_customer_phone_per_business"),)

# --- Conversation Model ---
class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, default="active", nullable=False)
    started_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_message_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    customer = relationship("Customer", back_populates="conversations")
    business = relationship("BusinessProfile", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    __table_args__ = (Index('idx_conversation_customer_business', 'customer_id', 'business_id'), Index('idx_conversation_status', 'status'),)

# --- Message Model ---
class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(
        SAEnum(
            MessageTypeEnum,
            name="message_type_enum",
            native_enum=False,
            values_callable=enum_values_callable,
            create_constraint=True
        ),
        nullable=False,
        index=True,
        default=MessageTypeEnum.OUTBOUND
    )
    status = Column(
        SAEnum(
            MessageStatusEnum,
            name="message_status_enum",
            native_enum=False,
            values_callable=enum_values_callable,
            create_constraint=True
        ),
        nullable=False,
        index=True,
        default=MessageStatusEnum.PENDING
    )
    sender_type = Column(
        SAEnum(
            SenderTypeEnum,
            name="message_sender_type_enum",
            native_enum=False,
            values_callable=enum_values_callable,
            create_constraint=True
        ),
        nullable=True, 
        index=True,
    )
    parent_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    scheduled_send_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    is_hidden = Column(Boolean, default=False, nullable=False)
    message_metadata = Column(JSON, nullable=True)
    twilio_message_sid = Column(String, nullable=True, index=True)
    source = Column(String, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")
    business = relationship("BusinessProfile", back_populates="messages")
    customer = relationship("Customer", back_populates="messages")
    parent = relationship("Message", remote_side=[id], backref=backref("children", cascade="all, delete-orphan"))
    # Relationships to AppointmentRequest - CORRECTED Syntax
    appointment_request_as_customer_initiated = relationship("AppointmentRequest", foreign_keys="AppointmentRequest.customer_initiated_message_id", back_populates="customer_initiated_message_ref", uselist=False)
    appointment_request_as_business_proposal = relationship("AppointmentRequest", foreign_keys="AppointmentRequest.business_proposal_message_id", back_populates="business_proposal_message_ref", uselist=False)
    appointment_request_as_customer_reply = relationship("AppointmentRequest", foreign_keys="AppointmentRequest.customer_reply_to_proposal_message_id", back_populates="customer_reply_to_proposal_message_ref", uselist=False)


    __table_args__ = (
        Index('idx_message_conversation', 'conversation_id'),
        Index('idx_message_customer', 'customer_id'),
        Index('idx_message_business', 'business_id'),
        Index('idx_message_type', 'message_type'),
        Index('idx_message_status', 'status'),
        Index('idx_message_sender_type', 'sender_type'),
        Index('idx_message_scheduled_send_at', 'scheduled_send_at'),
        Index('idx_message_source', 'source'),
    )

# --- RoadmapMessage Model ---
class RoadmapMessage(Base):
    __tablename__ = "roadmap_messages"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False)
    smsContent = Column(Text, nullable=False)
    smsTiming = Column(Text, nullable=False) # Expecting descriptive text or JSON string
    status = Column(
        SAEnum(
            MessageStatusEnum,
            name="roadmap_message_status_enum",
            native_enum=False,
            values_callable=enum_values_callable,
            create_constraint=True
        ),
        default=MessageStatusEnum.PENDING_REVIEW,
        nullable=False
    )
    send_datetime_utc = Column(DateTime(timezone=True), nullable=True)
    relevance = Column(Text, nullable=True)
    success_indicator = Column(Text, nullable=True)
    no_response_plan = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    message = relationship("Message")
    customer = relationship("Customer", back_populates="roadmap_messages")
    business = relationship("BusinessProfile", back_populates="roadmap_messages")
    __table_args__ = (Index('idx_roadmap_customer_business', 'customer_id', 'business_id'), Index('idx_roadmap_status', 'status'),)

    @property
    def timing_dict(self):
        if self.smsTiming:
            try:
                return json.loads(self.smsTiming) # CORRECTED: Use json.loads for JSON string
            except json.JSONDecodeError: # Handle case where it might not be valid JSON
                return {"description": self.smsTiming} # Or return empty dict / log error
        return {}

# --- Engagement Model ---
class Engagement(Base):
    __tablename__ = "engagements"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False)
    response = Column(Text, nullable=True)
    ai_response = Column(Text, nullable=True)
    status = Column(
        SAEnum(
            MessageStatusEnum,
            name="engagement_status_enum",
            native_enum=False,
            values_callable=enum_values_callable,
            create_constraint=True
        ),
        default=MessageStatusEnum.PENDING_REVIEW,
        nullable=False
    )
    parent_engagement_id = Column(Integer, ForeignKey("engagements.id", ondelete="SET NULL"), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    is_hidden = Column(Boolean, default=False, nullable=False, server_default='false')
    source = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    message_metadata = Column(JSON, nullable=True)

    message = relationship("Message")
    customer = relationship("Customer", back_populates="engagements")
    business = relationship("BusinessProfile", back_populates="engagements")
    parent_engagement = relationship("Engagement", remote_side=[id], backref=backref("child_engagements", cascade="all, delete-orphan"))

    __table_args__ = (
        Index('idx_engagement_customer_business', 'customer_id', 'business_id'),
        Index('idx_engagement_status', 'status'),
        Index('idx_engagement_is_hidden', 'is_hidden'),
        Index('idx_engagement_source', 'source'),
    )

# --- BusinessOwnerStyle Model ---
class BusinessOwnerStyle(Base):
    __tablename__ = "business_owner_styles"
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False, unique=True)
    scenario = Column(Text, nullable=True)
    response = Column(Text, nullable=True)
    context_type = Column(String, nullable=True)
    key_phrases = Column(JSON, nullable=True)
    style_notes = Column(JSON, nullable=True)
    personality_traits = Column(JSON, nullable=True)
    message_patterns = Column(JSON, nullable=True)
    special_elements = Column(JSON, nullable=True)
    last_analyzed = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    business = relationship("BusinessProfile", backref=backref("style_guide_settings", uselist=False))

    @property
    def style_guide(self):
        def _load_json_field(field_val, default_factory):
            if field_val is None:
                return default_factory()
            if isinstance(field_val, (dict, list)): # Already parsed
                return field_val
            if isinstance(field_val, str):
                try:
                    return json.loads(field_val) # CORRECTED: Use json.loads
                except json.JSONDecodeError:
                    # Consider logging this error
                    return default_factory()
            return default_factory() # Fallback for other unexpected types

        return {
            'key_phrases': _load_json_field(self.key_phrases, list),
            'style_notes': _load_json_field(self.style_notes, dict),
            'personality_traits': _load_json_field(self.personality_traits, list),
            'message_patterns': _load_json_field(self.message_patterns, dict),
            'special_elements': _load_json_field(self.special_elements, dict),
        }

# --- ConsentLog Model ---
class ConsentLog(Base):
    __tablename__ = "consent_log" # MODIFIED as per user request
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False)
    method = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    message_sid = Column(String, nullable=True)
    status = Column(
        SAEnum(
            OptInStatus,
            name="consent_log_status_enum",
            native_enum=False,
            values_callable=enum_values_callable,
            create_constraint=True
        ),
        nullable=False
    )
    sent_at = Column(DateTime(timezone=True), nullable=True)
    replied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    customer = relationship("Customer", back_populates="consent_logs")
    business = relationship("BusinessProfile", back_populates="consent_logs")
    __table_args__ = (Index('idx_consent_log_customer_business_status', 'customer_id', 'business_id', 'status'),)


# --- Tag Models ---
class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)

    business = relationship("BusinessProfile", back_populates="tags")
    customers = relationship("Customer", secondary="customer_tags", back_populates="tags")
    __table_args__ = (UniqueConstraint('business_id', 'name', name='uq_tag_name_per_business'),)

class CustomerTag(Base):
    __tablename__ = "customer_tags"
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

# --- AppointmentAvailability Model ---
class AppointmentAvailability(Base):
    __tablename__ = "appointment_availability"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week = Column(String, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False) # MODIFIED
    end_time = Column(DateTime(timezone=True), nullable=False)   # MODIFIED
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    business = relationship("BusinessProfile", back_populates="appointment_availabilities")
    __table_args__ = (Index('idx_appt_avail_business_day_active', 'business_id', 'day_of_week', 'is_active'),)

# --- AppointmentRequest Model ---
class AppointmentRequest(Base):
    __tablename__ = "appointment_requests"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_initiated_message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)
    business_proposal_message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_reply_to_proposal_message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)

    original_message_text = Column(Text, nullable=True)
    parsed_requested_time_text = Column(String, nullable=True)
    parsed_requested_datetime_utc = Column(DateTime(timezone=True), nullable=True)

    status = Column(
        SAEnum(
            AppointmentRequestStatusEnum,
            name="appointment_request_status_enum_v2",
            native_enum=False,
            values_callable=enum_values_callable,
            create_constraint=True
        ),
        default=AppointmentRequestStatusEnum.PENDING_OWNER_ACTION,
        nullable=False,
        index=True
    )
    resolution_type = Column(String, nullable=True, index=True)
    source = Column(
        SAEnum(
            AppointmentRequestSourceEnum,
            name="appointment_request_source_enum_v2",
            native_enum=False,
            values_callable=enum_values_callable,
            create_constraint=True
        ),
        nullable=False,
        index=True
    )
    ai_suggested_reply = Column(Text, nullable=True)
    confirmed_datetime_utc = Column(DateTime(timezone=True), nullable=True, index=True)
    owner_suggested_time_text = Column(String, nullable=True)
    owner_suggested_datetime_utc = Column(DateTime(timezone=True), nullable=True)
    customer_reschedule_suggestion = Column(Text, nullable=True)
    owner_actioned_at = Column(DateTime(timezone=True), nullable=True)
    owner_removed_reason = Column(Text, nullable=True)
    details = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    business = relationship("BusinessProfile", back_populates="appointment_requests")
    customer = relationship("Customer", back_populates="appointment_requests")
    # Message relationships - CORRECTED Syntax
    customer_initiated_message_ref = relationship("Message", foreign_keys=[customer_initiated_message_id], back_populates="appointment_request_as_customer_initiated")
    business_proposal_message_ref = relationship("Message", foreign_keys=[business_proposal_message_id], back_populates="appointment_request_as_business_proposal")
    customer_reply_to_proposal_message_ref = relationship("Message", foreign_keys=[customer_reply_to_proposal_message_id], back_populates="appointment_request_as_customer_reply")

    __table_args__ = (
        Index('idx_appt_req_business_customer_status', 'business_id', 'customer_id', 'status'),
        Index('idx_appt_req_confirmed_time', 'confirmed_datetime_utc'),
    )