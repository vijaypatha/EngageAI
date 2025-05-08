from pydantic import BaseModel, constr, Field, EmailStr, validator
from typing import Optional, Annotated, List, Dict, Any
import pytz
from datetime import datetime
import uuid
import re # Added for regex operations in validator

# Helper function to normalize phone numbers
def normalize_phone_number(cls, v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', v)
    
    # If 10 digits, assume US number and prepend +1
    if len(digits) == 10:
        return f"+1{digits}"
    # If 11 digits and starts with 1 (e.g., 13856268825), prepend +
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    # If already starts with +, assume it's in a valid format (or close enough)
    # Also ensure only digits remain after the +
    elif v.startswith('+'):
        return f"+{re.sub(r'\D', '', v[1:])}"
    # For other cases, if it's all digits but not matching above, prepend +
    # This is a fallback, might need adjustment based on expected non-US formats
    elif digits.isdigit() and len(digits) > 0 : # Check if it became all digits
        return f"+{digits}"
        
    # If the input (after initial stripping of non-digits) was not purely digits or not a recognized format
    # return v # Fallback for unrecognized formats, or you could raise ValueError
    # Let's raise a ValueError for inputs that aren't clearly phone numbers after processing
    raise ValueError(f"Invalid phone number format: {v}")


# --- Add these Tag schemas ---
class TagBase(BaseModel):
    name: constr(strip_whitespace=True, to_lower=True, min_length=1, max_length=100)

class TagCreate(TagBase):
    pass

class TagRead(TagBase):
    id: int
    # business_id: int # Optional: Decide if frontend needs this when reading a tag

    class Config:
        from_attributes = True

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

    _normalize_business_phone = validator('business_phone_number', pre=True, allow_reuse=True)(normalize_phone_number)

class BusinessProfileCreate(BusinessProfileBase):
    pass

class BusinessProfileUpdate(BaseModel):
    business_name: Optional[str] = None
    industry: Optional[str] = None
    business_goal: Optional[str] = None
    primary_services: Optional[str] = None
    representative_name: Optional[str] = None
    timezone: Optional[str] = None
    twilio_number: Optional[str] = None # Typically assigned by system, not direct update
    business_phone_number: Optional[str] = None

    _normalize_business_phone_update = validator('business_phone_number', pre=True, allow_reuse=True)(normalize_phone_number)
    _normalize_twilio_number_update = validator('twilio_number', pre=True, allow_reuse=True)(normalize_phone_number)


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

    _normalize_business_phone = validator('business_phone_number', pre=True, allow_reuse=True)(normalize_phone_number)

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

    _normalize_customer_phone = validator('phone', pre=True, allow_reuse=True)(normalize_phone_number)

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

    _normalize_customer_phone_update = validator('phone', pre=True, allow_reuse=True)(normalize_phone_number)

class Customer(CustomerBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    latest_consent_status: Optional[str] = None
    latest_consent_updated: Optional[datetime] = None
    tags: List[TagRead] = []

    class Config:
        from_attributes = True

### ✅ SMS Schemas
class SMSCreate(BaseModel):
    customer_id: int
    message: constr(max_length=160)
    send_time: Optional[str] = None

    @validator('message')
    def validate_message_length(cls, v):
        if len(v) > 160:
            raise ValueError("Message length exceeds 160 characters")
        return v

class SMSUpdate(BaseModel):
    updated_message: str
    status: str
    send_time: Optional[str] = None

class SMSApproveOnly(BaseModel):
    status: str

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
    tone: str # This field and below might be part of analysis, not direct input for training response
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
    send_datetime_utc: Optional[str] = None # Should be datetime if used for calculations
    customer_timezone: Optional[str] = None

    class Config:
        orm_mode = True

class AllRoadmapMessagesResponse(BaseModel):
    total: int
    scheduledThisWeek: int
    messages: list[RoadmapMessageOut]

class ConversationMessage(BaseModel):
    sender: str
    text: str
    timestamp: Optional[str] = None # Should be datetime
    source: str
    direction: str

class ConversationResponse(BaseModel):
    customer: dict
    messages: List[ConversationMessage]

class ScheduledSMSOut(BaseModel):
    id: int
    customer_id: int
    business_id: int
    message: str
    status: str
    send_time: str # Should be datetime
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
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Engagement Schemas
class EngagementBase(BaseModel):
    message_id: int # Should this be optional if an engagement can start from customer?
    customer_id: int
    business_id: int
    response: str # Customer's response
    ai_response: Optional[str] = None
    status: str = "pending_review"
    parent_engagement_id: Optional[int] = None
    sent_at: Optional[datetime] = None # When AI response was sent

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
    message_id: Optional[int] = None # Making optional if not always linked to a Message table ID initially
    customer_id: int
    business_id: int
    smsContent: str
    smsTiming: str # This might be descriptive like "Day 5, 10:00 AM"
    status: str = "pending_review"
    send_datetime_utc: Optional[datetime] = None # Actual UTC time for sending
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

# Scheduled SMS Schemas (Potentially redundant with Message model if message_type='scheduled')
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
    status: str = "pending" # e.g. pending, opted_in, opted_out, declined
    sent_at: Optional[datetime] = None # When the opt-in request was sent
    replied_at: Optional[datetime] = None # When the customer replied

    _normalize_consent_phone = validator('phone_number', pre=True, allow_reuse=True)(normalize_phone_number)

class ConsentLogCreate(ConsentLogBase):
    # sent_at will be set by the service, make it optional here or remove if not user-provided
    sent_at: Optional[datetime] = Field(default_factory=datetime.utcnow)


class ConsentLogUpdate(BaseModel):
    status: Optional[str] = None
    replied_at: Optional[datetime] = None

class ConsentLog(ConsentLogBase):
    id: int
    # created_at: datetime # If you have these in your model
    # updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class RoadmapMessageResponse(BaseModel):
    id: int
    customer_id: int
    business_id: int
    message: str = Field(..., alias='smsContent')
    scheduled_time: datetime = Field(..., alias='send_datetime_utc')
    status: str
    # relevance: Optional[str] = Field(None, alias='relevance')
    # success_indicator: Optional[str] = Field(None, alias='success_indicator')
    # no_response_plan: Optional[str] = Field(None, alias='no_response_plan')
    # created_at: datetime
    # updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True

class RoadmapGenerate(BaseModel):
    customer_id: int
    business_id: int
    context: Optional[Dict[str, Any]] = None

class RoadmapResponse(BaseModel):
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
    business_id: int
    phone_number: str

    _normalize_twilio_phone = validator('phone_number', pre=True, allow_reuse=True)(normalize_phone_number)

class ConsentBase(BaseModel): # This is a duplicate of the earlier ConsentBase. Consolidate if identical.
    customer_id: int
    business_id: int
    phone_number: str # Already has validator in its original definition
    status: str = "awaiting_optin"

    # Re-applying validator here for clarity if this definition is used independently
    _normalize_consent_phone_2 = validator('phone_number', pre=True, allow_reuse=True)(normalize_phone_number)


class ConsentCreate(ConsentBase):
    pass

class ConsentResponse(ConsentBase):
    id: int
    method: str
    replied_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    message_sid: Optional[str] = None
    # created_at: datetime # Add if in model and needed
    # updated_at: Optional[datetime] = None # Add if in model and needed

    class Config:
        from_attributes = True

class BusinessScenarioCreate(BaseModel):
    scenario: str = Field(..., description="The scenario description")
    context_type: str = Field(..., description="The type of context (e.g., inquiry, appreciation, follow_up)")
    # The fields below are more for the *output* of style analysis, not typical input for creating a scenario response
    key_phrases: Optional[List[str]] = Field(default=[])
    style_notes: Optional[Dict[str, Any]] = Field(default={})
    personality_traits: Optional[List[str]] = Field(default=[])
    # message_patterns used to be List[str], ensure consistency with model or analysis output
    message_patterns: Optional[Dict[str, Any]] = Field(default={}) # Changed to Dict to match StyleAnalysis
    special_elements: Optional[Dict[str, Any]] = Field(default={})
    response: Optional[str] = Field(default="", description="The response to the scenario")

class BusinessOwnerStyleResponse(BaseModel):
    id: int
    business_id: int
    scenario: str
    response: str
    context_type: str
    last_analyzed: Optional[datetime] = None

    class Config:
        from_attributes = True