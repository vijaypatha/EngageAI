# backend/app/models.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, UniqueConstraint, Index, JSON, func
from sqlalchemy.orm import relationship, backref # Keep backref if used elsewhere, but we'll fix Tag specifically
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from app.database import Base
import datetime
import uuid
import json # Keep if used by your @property

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
    industry = Column(String) # If these can be null in DB based on your schema, add nullable=True
    business_goal = Column(String)
    primary_services = Column(String)
    representative_name = Column(String)
    timezone = Column(String, default="UTC")
    twilio_number = Column(String, nullable=True)
    twilio_sid = Column(String, nullable=True)
    messaging_service_sid = Column(String, nullable=True)
    business_phone_number = Column(String, nullable=True) # Owner's personal phone
    slug = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, nullable=True, onupdate=utc_now) # Added onupdate

    # --- START: AUTOPILOT FIELDS TO ADD ---
    notify_owner_on_reply_with_link = Column(Boolean, default=False, nullable=False)
    enable_ai_faq_auto_reply = Column(Boolean, default=False, nullable=False)
    structured_faq_data = Column(JSON, nullable=True)
    # --- END: AUTOPILOT FIELDS TO ADD ---

    # Relationships
    customers = relationship("Customer", back_populates="business", cascade="all, delete-orphan") # Added cascade
    conversations = relationship("Conversation", back_populates="business", cascade="all, delete-orphan") # Added cascade
    messages = relationship("Message", back_populates="business", cascade="all, delete-orphan") # Added cascade
    engagements = relationship("Engagement", back_populates="business", cascade="all, delete-orphan") # Added cascade
    roadmap_messages = relationship("RoadmapMessage", back_populates="business", cascade="all, delete-orphan") # Added cascade
    # scheduled_sms relationship was in your schemas, ensure it's defined if you have this model
    scheduled_sms = relationship("ScheduledSMS", back_populates="business", cascade="all, delete-orphan") # Added cascade
    consent_logs = relationship("ConsentLog", back_populates="business", cascade="all, delete-orphan") # Added cascade
    
    # --- MODIFIED RELATIONSHIP to Tag (Fix for Mapper Error) ---
    tags = relationship(
        "Tag",
        back_populates="business", # This means Tag model needs a 'business' attribute linking back
        cascade="all, delete-orphan"
    )
    # --- END MODIFIED RELATIONSHIP ---

    # If BusinessOwnerStyle exists and needs to link back:
    # business_owner_styles = relationship("BusinessOwnerStyle", back_populates="business_profile_relation_name", cascade="all, delete-orphan")


class Customer(Base): # YOUR ORIGINAL, just ensure back_populates are correct
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
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True, onupdate=utc_now) # Added onupdate

    business = relationship("BusinessProfile", back_populates="customers")
    conversations = relationship("Conversation", back_populates="customer", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="customer", cascade="all, delete-orphan")
    engagements = relationship("Engagement", back_populates="customer", cascade="all, delete-orphan")
    roadmap_messages = relationship("RoadmapMessage", back_populates="customer", cascade="all, delete-orphan")
    scheduled_sms = relationship("ScheduledSMS", back_populates="customer", cascade="all, delete-orphan")
    consent_logs = relationship("ConsentLog", back_populates="customer", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary="customer_tags", back_populates="customers") # Changed from backref

    __table_args__ = (UniqueConstraint("phone", "business_id", name="unique_customer_phone_per_business"),)


class Conversation(Base): # YOUR ORIGINAL, ensure back_populates
    __tablename__ = "conversations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE")) # Added ondelete
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE")) # Added ondelete
    status = Column(String, default="active")
    started_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    last_message_at = Column(TIMESTAMP(timezone=True), default=utc_now)

    customer = relationship("Customer", back_populates="conversations")
    business = relationship("BusinessProfile", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    __table_args__ = (Index('idx_conversation_customer', 'customer_id'), Index('idx_conversation_business', 'business_id'), Index('idx_conversation_status', 'status'),)


class Message(Base): # YOUR ORIGINAL, ensure back_populates
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE")) # Added ondelete
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="SET NULL"), nullable=True) # Business deletion might nullify, or cascade
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True) # Customer deletion might nullify, or cascade
    content = Column(Text)
    message_type = Column(String)
    status = Column(String, default="pending_review")
    parent_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    scheduled_time = Column(TIMESTAMP(timezone=True), nullable=True)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    is_hidden = Column(Boolean, default=False)
    message_metadata = Column(JSON, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)

    conversation = relationship("Conversation", back_populates="messages")
    business = relationship("BusinessProfile", back_populates="messages")
    customer = relationship("Customer", back_populates="messages")
    parent = relationship("Message", remote_side=[id]) # For self-referential relationship
    # engagements = relationship("Engagement", back_populates="message", cascade="all, delete-orphan") # If Engagement links back to Message
    # roadmap_message_link = relationship("RoadmapMessage", back_populates="message_obj", uselist=False) # If RoadmapMessage links to this

    __table_args__ = (Index('idx_message_conversation', 'conversation_id'), Index('idx_message_customer', 'customer_id'), Index('idx_message_business', 'business_id'), Index('idx_message_type', 'message_type'), Index('idx_message_status', 'status'), Index('idx_message_scheduled', 'scheduled_time'),)


class RoadmapMessage(Base): # YOUR ORIGINAL, ensure back_populates
    __tablename__ = "roadmap_messages"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True) # Link to actual Message when scheduled/sent
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE")) # Cascade if customer deleted
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE")) # Cascade if business deleted
    smsContent = Column(Text)
    smsTiming = Column(Text)
    status = Column(String, default="pending_review")
    send_datetime_utc = Column(TIMESTAMP(timezone=True), nullable=True)
    relevance = Column(Text, nullable=True)
    success_indicator = Column(Text, nullable=True)
    no_response_plan = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True, onupdate=utc_now)

    message = relationship("Message") # This is a one-to-one or one-to-many from RoadmapMessage to Message if message_id is populated
    customer = relationship("Customer", back_populates="roadmap_messages")
    business = relationship("BusinessProfile", back_populates="roadmap_messages")
    # scheduled_sms_link = relationship("ScheduledSMS", back_populates="roadmap_message_obj", uselist=False) # If ScheduledSMS links to this

    __table_args__ = (Index('idx_roadmap_customer', 'customer_id'), Index('idx_roadmap_business', 'business_id'), Index('idx_roadmap_status', 'status'),)
    @property
    def timing_dict(self):
        try: return json.loads(self.smsTiming)
        except: return {}


class Engagement(Base): # YOUR ORIGINAL, ensure back_populates
    __tablename__ = "engagements"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True) # Message this engagement is related to (e.g. AI response became this Message)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"))
    response = Column(Text, nullable=True) # Customer's inbound text
    ai_response = Column(Text, nullable=True) # AI/Business outbound text
    status = Column(String, default="pending_review")
    parent_engagement_id = Column(Integer, ForeignKey("engagements.id"), nullable=True)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True, onupdate=utc_now)
    message_metadata = Column(JSON, nullable=True) # Your original had this

    message = relationship("Message") # Relationship to the Message table
    customer = relationship("Customer", back_populates="engagements")
    business = relationship("BusinessProfile", back_populates="engagements")
    parent_engagement = relationship("Engagement", remote_side=[id])
    __table_args__ = (Index('idx_engagement_customer', 'customer_id'), Index('idx_engagement_business', 'business_id'), Index('idx_engagement_status', 'status'), Index('idx_engagement_sent', 'sent_at'),)


class BusinessOwnerStyle(Base): # YOUR ORIGINAL
    __tablename__ = "business_owner_styles"
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False) # Added ondelete
    scenario = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    context_type = Column(String, nullable=False)
    key_phrases = Column(JSON, nullable=True)
    style_notes = Column(JSON, nullable=True)
    personality_traits = Column(JSON, nullable=True)
    message_patterns = Column(JSON, nullable=True)
    special_elements = Column(JSON, nullable=True)
    last_analyzed = Column(TIMESTAMP(timezone=True), default=utc_now)
    
    # Corrected relationship assuming BusinessProfile has 'business_owner_styles'
    business = relationship("BusinessProfile") # If BusinessProfile has `styles = relationship("BusinessOwnerStyle", back_populates="business_profile_object_name")`
                                              # then this should be `business_profile_object_name = relationship("BusinessProfile", back_populates="styles")`
                                              # For simplicity, if BusinessProfile doesn't have a collection of styles, this simple 'business' is okay.
                                              # However, if BusinessProfile has 'business_owner_styles = relationship("BusinessOwnerStyle", back_populates="business_profile_relation_name")'
                                              # then this should be: business_profile_relation_name = relationship("BusinessProfile", back_populates="business_owner_styles")
                                              # Let's assume the simple 'business' works for now or your BusinessProfile handles the back_populates for this.


    @property
    def style_guide(self):
        # ... (your original property) ...
        return {
            'key_phrases': json.loads(self.key_phrases) if self.key_phrases else [],
            'style_notes': json.loads(self.style_notes) if self.style_notes else {'tone': '', 'formality_level': '', 'personal_touches': [], 'authenticity_markers': []},
            'personality_traits': json.loads(self.personality_traits) if self.personality_traits else [],
            'message_patterns': json.loads(self.message_patterns) if self.message_patterns else {'greetings': [], 'closings': [], 'transitions': [], 'emphasis_patterns': []},
            'special_elements': json.loads(self.special_elements) if self.special_elements else {'industry_terms': [], 'metaphors': [], 'personal_references': [], 'emotional_markers': []}
        }


class ConsentLog(Base): # YOUR ORIGINAL, ensure back_populates
    __tablename__ = "consent_log"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"))
    method = Column(String)
    phone_number = Column(String)
    message_sid = Column(String, nullable=True)
    status = Column(String, default="pending")
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True) # Made nullable as per your schema
    replied_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True, onupdate=utc_now)

    customer = relationship("Customer", back_populates="consent_logs")
    business = relationship("BusinessProfile", back_populates="consent_logs")


class ScheduledSMS(Base): # YOUR ORIGINAL, ensure back_populates
    __tablename__ = "scheduled_sms"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"))
    message = Column(Text)
    status = Column(String, default="scheduled")
    send_time = Column(DateTime) # Your original had DateTime, not TIMESTAMP with timezone
    source = Column(String, nullable=True)
    roadmap_id = Column(Integer, ForeignKey("roadmap_messages.id", ondelete="SET NULL"), nullable=True) # Link to RoadmapMessage
    is_hidden = Column(Boolean, default=False)
    business_timezone = Column(String)
    customer_timezone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    customer = relationship("Customer", back_populates="scheduled_sms")
    business = relationship("BusinessProfile", back_populates="scheduled_sms")
    # If RoadmapMessage needs to link back to ScheduledSMS:
    roadmap = relationship("RoadmapMessage") # This implies RoadmapMessage.scheduled_sms_link or similar
                                           # Or if this is just a simple FK link, it's fine.


class Tag(Base): # YOUR ORIGINAL, with corrected relationship to BusinessProfile
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)

    # --- THIS IS THE FIX FOR THE MAPPER ERROR ---
    business = relationship(
        "BusinessProfile",
        back_populates="tags" # This matches BusinessProfile.tags relationship name
    )
    # --- END FIX ---

    # Relationship to customers via customer_tags (many-to-many)
    customers = relationship(
        "Customer",
        secondary="customer_tags",
        back_populates="tags" # Requires Customer model to have tags = relationship(..., back_populates="customers")
    )

    __table_args__ = (UniqueConstraint('business_id', 'name', name='uq_tag_name_per_business'), Index('idx_tag_business_name', 'business_id', 'name'),)


class CustomerTag(Base): # YOUR ORIGINAL (Association Table)
    __tablename__ = "customer_tags"
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    # No explicit relationships needed here typically for a simple association table
    # SQLAlchemy handles it via the `secondary` argument in the `Customer` and `Tag` models if they have a many-to-many.