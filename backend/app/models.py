from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base
import datetime


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
    business = relationship("BusinessProfile")

class RoadmapMessage(Base):
    __tablename__ = "roadmap_messages"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    business_id = Column(Integer, ForeignKey("business_profiles.id"))
    smsContent = Column(Text)
    smsTiming = Column(String)
    status = Column(String)
    send_datetime_utc = Column(DateTime, nullable=True) 

    customer = relationship("Customer", back_populates="roadmap_messages")