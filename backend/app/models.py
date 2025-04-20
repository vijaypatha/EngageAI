from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.database import Base
import datetime
import json


class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String, unique=True, index=True)
    slug = Column(String, unique=True, index=True)
    industry = Column(String)
    business_goal = Column(String, nullable=True)
    primary_services = Column(String, nullable=True)
    representative_name = Column(String, nullable=True)
    twilio_number = Column(String, nullable=True)
    

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, index=True)
    phone = Column(String, index=True)
    lifecycle_stage = Column(String, nullable=True)
    pain_points = Column(Text, nullable=True)
    interaction_history = Column(Text, nullable=True)

    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    business = relationship("BusinessProfile")
    roadmap_messages = relationship("RoadmapMessage", back_populates="customer")
    is_generating_roadmap = Column(Boolean, default=False)  # <-- ADD THIS LINE
    opted_in = Column(Boolean, nullable=True)
    last_generation_attempt = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("phone", "business_id", name="unique_customer_phone_per_business"),
    )


class ScheduledSMS(Base):
    __tablename__ = "scheduled_sms"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False) 
    message = Column(Text)
    status = Column(String, default="pending_review")
    send_time = Column(DateTime, default=datetime.datetime.utcnow)
    customer = relationship("Customer")
    source = Column(String, nullable=True)  # e.g., 'instant_nudge', 'roadmap'
    roadmap_id = Column(Integer, ForeignKey("roadmap_messages.id"), nullable=True)  # <-- ADD THIS LINE
    roadmap_message = relationship("RoadmapMessage")  # <-- ADD THIS LINE
    is_hidden = Column(Boolean, default=False)  # <-- ADD THIS LINE

class Engagement(Base):
    __tablename__ = "engagements"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    response = Column(Text)
    ai_response = Column(Text, nullable=True)
    status = Column(String, default="pending_review")
    customer = relationship("Customer")
    sent_at = Column(DateTime, nullable=True)  

class BusinessOwnerStyle(Base):
    __tablename__ = "business_owner_styles"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id"))
    scenario = Column(Text)
    response = Column(Text)
    context_type = Column(String)  # 'inquiry', 'complaint', 'follow_up', etc.
    key_phrases = Column(Text)  # JSON array of common phrases
    style_notes = Column(Text)  # JSON object with style analysis
    personality_traits = Column(Text)  # JSON array of identified traits
    message_patterns = Column(Text)  # JSON array of common patterns
    special_elements = Column(Text)  # JSON object with unique elements
    last_analyzed = Column(DateTime, default=datetime.datetime.utcnow)
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

class RoadmapMessage(Base):
    __tablename__ = "roadmap_messages"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    business_id = Column(Integer, ForeignKey("business_profiles.id"))
    smsContent = Column(Text)
    smsTiming = Column(Text)  # Changed to Text to store JSON string
    status = Column(String)
    send_datetime_utc = Column(DateTime, nullable=True)
    relevance = Column(Text, nullable=True)  # Added
    success_indicator = Column(Text, nullable=True)  # Added
    no_response_plan = Column(Text, nullable=True)  # Added

    customer = relationship("Customer", back_populates="roadmap_messages")

    @property
    def timing_dict(self):
        """Return the smsTiming as a dictionary"""
        try:
            return json.loads(self.smsTiming)
        except:
            return {}

class ConsentLog(Base):
    __tablename__ = "consent_log"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    method = Column(String, nullable=False)  # e.g., "double_opt_in"
    phone_number = Column(String, nullable=False)
    message_sid = Column(String, nullable=True)
    status = Column(String, default="pending")  # "pending", "opted_in", "declined", "stopped"
    sent_at = Column(DateTime, default=datetime.datetime.utcnow)
    replied_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_consent_customer_replied', 'customer_id', 'replied_at'),
    )