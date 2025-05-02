from pydantic import BaseModel, constr, Field, EmailStr, validator
from typing import Optional, Annotated, List, Dict, Any
import pytz
from datetime import datetime
import uuid

### ✅ Timezone Schemas
class TimezoneInfo(BaseModel):
    timezone: str
    display_name: str
    offset: str

    @validator('timezone')
    def validate_timezone(cls, v):
        try:
            pytz.timezone(v)
            return v
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f"Invalid timezone: {v}")

### ✅ Business Schemas
class BusinessProfileBase(BaseModel):
    business_name: str
    industry: str
    business_goal: str
    primary_services: str
    representative_name: str
    timezone: Optional[str] = "UTC"
    business_phone_number: Optional[str] = None

class BusinessProfileCreate(BusinessProfileBase):
    pass

class BusinessProfileUpdate(BaseModel):
    business_name: Optional[str] = None
    industry: Optional[str] = None
    business_goal: Optional[str] = None
    primary_services: Optional[str] = None
    representative_name: Optional[str] = None
    timezone: Optional[str] = None
    twilio_number: Optional[str] = None
    business_phone_number: Optional[str] = None

class BusinessProfile(BusinessProfileBase):
    id: int
    twilio_number: Optional[str] = None
    slug: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class BusinessPhoneUpdate(BaseModel):
    business_phone_number: str

    class Config:
        from_attributes = True

### ✅ Customer Schemas
class CustomerBase(BaseModel):
    customer_name: str
    phone: str
    lifecycle_stage: str
    pain_points: str
    interaction_history: str
    business_id: int
    timezone: Optional[str] = None
    opted_in: Optional[bool] = None
    is_generating_roadmap: Optional[bool] = False
    last_generation_attempt: Optional[datetime] = None

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    pain_points: Optional[str] = None
    interaction_history: Optional[str] = None
    timezone: Optional[str] = None
    opted_in: Optional[bool] = None

class Customer(CustomerBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    latest_consent_status: Optional[str] = None
    latest_consent_updated: Optional[datetime] = None

    class Config:
        from_attributes = True

### ✅ SMS Schemas
class SMSCreate(BaseModel):
    customer_id: int
    message: constr(max_length=160)  # Enforces SMS character limit
    send_time: Optional[str] = None  # ISO format datetime string in business timezone

    @validator('message')
    def validate_message_length(cls, v):
        if len(v) > 160:
            raise ValueError("Message length exceeds 160 characters")
        return v

class SMSUpdate(BaseModel):
    updated_message: str
    status: str
    send_time: Optional[str] = None  # ISO format datetime string in business timezone

class SMSApproveOnly(BaseModel):
    status: str  # Just 'scheduled'

### ✅ Engagement Schema
class EngagementResponse(BaseModel):
    customer_id: int
    response: str

### ✅ SMS Style Schema
class SMSStyleInput(BaseModel):
    business_id: int
    scenario: str
    response: str
    context_type: str
    tone: str
    language_style: str
    key_phrases: List[str]
    formatting_preferences: Dict[str, Any]

class StyleAnalysis(BaseModel):
    key_phrases: List[str]
    style_notes: Dict[str, Any]
    personality_traits: List[str]
    message_patterns: Dict[str, Any]
    special_elements: Dict[str, Any]
    overall_summary: str  

class SMSStyleResponse(BaseModel):
    status: str
    message: Optional[str] = None
    updated_count: Optional[int] = None
    updated_styles: Optional[List[Dict[str, Any]]] = None
    style_analysis: Optional[StyleAnalysis] = None

    class Config:
        from_attributes = True

class RoadmapMessageOut(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    smsContent: str
    smsTiming: str
    status: str
    send_datetime_utc: Optional[str] = None
    customer_timezone: Optional[str] = None

    class Config:
        orm_mode = True

class AllRoadmapMessagesResponse(BaseModel):
    total: int
    scheduledThisWeek: int
    messages: list[RoadmapMessageOut]

class ConversationMessage(BaseModel):
    sender: str  # "customer", "ai", or "owner"
    text: str
    timestamp: Optional[str] = None
    source: str  # "ai_draft", "manual_reply", "scheduled_sms", "customer_response"
    direction: str  # "incoming" or "outgoing"

class ConversationResponse(BaseModel):
    customer: dict  # Contains "id" and "name"
    messages: List[ConversationMessage]

class ScheduledSMSOut(BaseModel):
    id: int
    customer_id: int
    business_id: int
    message: str
    status: str
    send_time: str
    source: Optional[str] = None
    roadmap_id: Optional[int] = None
    is_hidden: bool
    business_timezone: str
    customer_timezone: Optional[str] = None

    class Config:
        orm_mode = True

# Conversation Schemas
class ConversationBase(BaseModel):
    customer_id: int
    business_id: int
    status: str = "active"

class ConversationCreate(ConversationBase):
    pass

class ConversationUpdate(BaseModel):
    status: Optional[str] = None

class Conversation(ConversationBase):
    id: uuid.UUID
    started_at: datetime
    last_message_at: datetime

    class Config:
        from_attributes = True

# Message Schemas
class MessageBase(BaseModel):
    conversation_id: uuid.UUID
    business_id: int
    customer_id: int
    content: str
    message_type: str
    status: str = "pending_review"
    parent_id: Optional[int] = None
    scheduled_time: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    is_hidden: bool = False
    message_metadata: Optional[dict] = None

class MessageCreate(MessageBase):
    pass

class MessageUpdate(BaseModel):
    content: Optional[str] = None
    status: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    is_hidden: Optional[bool] = None
    message_metadata: Optional[dict] = None

class Message(MessageBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class MessageResponse(MessageBase):
    """Schema for message responses"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Engagement Schemas
class EngagementBase(BaseModel):
    message_id: int
    customer_id: int
    business_id: int
    response: str
    ai_response: Optional[str] = None
    status: str = "pending_review"
    parent_engagement_id: Optional[int] = None
    sent_at: Optional[datetime] = None

class EngagementCreate(EngagementBase):
    pass

class EngagementUpdate(BaseModel):
    response: Optional[str] = None
    ai_response: Optional[str] = None
    status: Optional[str] = None
    sent_at: Optional[datetime] = None

class Engagement(EngagementBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Roadmap Message Schemas
class RoadmapMessageBase(BaseModel):
    message_id: int
    customer_id: int
    business_id: int
    smsContent: str
    smsTiming: str
    status: str = "pending_review"
    send_datetime_utc: Optional[datetime] = None
    relevance: Optional[str] = None
    success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None

class RoadmapMessageCreate(RoadmapMessageBase):
    pass

class RoadmapMessageUpdate(BaseModel):
    smsContent: Optional[str] = None
    smsTiming: Optional[str] = None
    status: Optional[str] = None
    send_datetime_utc: Optional[datetime] = None
    relevance: Optional[str] = None
    success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None

class RoadmapMessage(RoadmapMessageBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Scheduled SMS Schemas
class ScheduledSMSBase(BaseModel):
    customer_id: int
    business_id: int
    message: str
    status: str = "scheduled"
    send_time: datetime
    source: Optional[str] = None
    roadmap_id: Optional[int] = None
    is_hidden: bool = False
    business_timezone: str
    customer_timezone: Optional[str] = None

class ScheduledSMSCreate(ScheduledSMSBase):
    pass

class ScheduledSMSUpdate(BaseModel):
    message: Optional[str] = None
    status: Optional[str] = None
    send_time: Optional[datetime] = None
    is_hidden: Optional[bool] = None

class ScheduledSMSResponse(ScheduledSMSBase):
    """Schema for scheduled SMS responses"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Consent Log Schemas
class ConsentLogBase(BaseModel):
    customer_id: int
    business_id: int
    method: str
    phone_number: str
    message_sid: Optional[str] = None
    status: str = "pending"
    sent_at: datetime
    replied_at: Optional[datetime] = None

class ConsentLogCreate(ConsentLogBase):
    pass

class ConsentLogUpdate(BaseModel):
    status: Optional[str] = None
    replied_at: Optional[datetime] = None

class ConsentLog(ConsentLogBase):
    id: int

    class Config:
        from_attributes = True


class RoadmapMessageResponse(BaseModel):
    """Schema for roadmap message responses"""
    id: int
    customer_id: int
    business_id: int
    # Alias 'message' schema field to the model's 'smsContent' column
    message: str = Field(..., alias='smsContent')
    # Alias 'scheduled_time' schema field to the model's 'send_datetime_utc' column
    scheduled_time: datetime = Field(..., alias='send_datetime_utc')
    status: str
    # Add other fields from the model you might need in the response schema,
    # with aliases if their names differ from the model
    # Example (add these if they should be in the response):
    # relevance: Optional[str] = Field(None, alias='relevance')
    # success_indicator: Optional[str] = Field(None, alias='success_indicator')
    # no_response_plan: Optional[str] = Field(None, alias='no_response_plan')
    # created_at: datetime = Field(..., alias='created_at')
    # updated_at: Optional[datetime] = Field(None, alias='updated_at')


    class Config:
        from_attributes = True # Keep this
        populate_by_name = True # Add this line

class RoadmapGenerate(BaseModel):
    """Schema for generating a new roadmap of messages for a customer"""
    customer_id: int
    business_id: int
    context: Optional[Dict[str, Any]] = None

class RoadmapResponse(BaseModel):
    """Schema for roadmap generation response"""
    status: str
    message: Optional[str] = None
    roadmap: Optional[List[RoadmapMessageResponse]] = None
    total_messages: Optional[int] = None
    customer_info: Optional[Dict[str, Any]] = None
    business_info: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

# Twilio Schemas
class TwilioNumberAssign(BaseModel):
    """Schema for assigning a Twilio number to a business"""
    business_id: int
    phone_number: str

    @validator('phone_number')
    def validate_phone_number(cls, v):
        # Remove any spaces or special characters except +
        v = ''.join(c for c in v if c.isdigit() or c == '+')
        if not v.startswith('+'):
            v = '+' + v
        return v

class ConsentBase(BaseModel):
    customer_id: int
    business_id: int
    phone_number: str
    status: str = "awaiting_optin"  # or "opted_in" / "opted_out"

class ConsentCreate(ConsentBase):
    """Schema for creating a new consent record"""
    pass

class ConsentResponse(ConsentBase):
    id: int
    method: str
    replied_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    message_sid: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class BusinessScenarioCreate(BaseModel):
    """Schema for creating a new business scenario."""
    scenario: str = Field(..., description="The scenario description")
    context_type: str = Field(..., description="The type of context (e.g., inquiry, appreciation, follow_up)")
    key_phrases: Optional[List[str]] = Field(default=[], description="Key phrases that characterize the business's style")
    style_notes: Optional[Dict[str, Any]] = Field(default={}, description="Additional style-related notes")
    personality_traits: Optional[List[str]] = Field(default=[], description="Personality traits to reflect in responses")
    message_patterns: Optional[List[str]] = Field(default=[], description="Common message patterns to follow")
    special_elements: Optional[Dict[str, Any]] = Field(default={}, description="Special elements to include in responses")
    response: Optional[str] = Field(default="", description="The response to the scenario")

class BusinessOwnerStyleResponse(BaseModel):
    """Schema for business owner style responses."""
    id: int
    business_id: int
    scenario: str
    response: str
    context_type: str
    last_analyzed: Optional[datetime] = None

    class Config:
        from_attributes = True