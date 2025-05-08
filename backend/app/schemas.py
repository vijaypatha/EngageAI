# backend/app/schemas.py

from pydantic import BaseModel, constr, Field, EmailStr, validator
from typing import Optional, Annotated, List, Dict, Any, StringConstraints
import pytz
from datetime import datetime
import uuid
import re # Added for regex operations in validator

# Helper function to normalize phone numbers
def normalize_phone_number(cls, v: Optional[str]) -> Optional[str]:
    if v is None:
        return None

    # Remove leading/trailing whitespace first
    v_stripped = v.strip()

    # Remove all non-digit characters for length checks, KEEP '+' if present at start
    digits = re.sub(r'\D', '', v_stripped)
    
    # If 10 digits (North America without country code)
    if len(digits) == 10:
        return f"+1{digits}"
    # If 11 digits and starts with 1 (North America with country code)
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}" # Already includes the 1
    # If the *original* input started with '+' (E.164 or similar)
    elif v_stripped.startswith('+'):
        # Keep the '+' and remove non-digits from the rest
        digits_after_plus = re.sub(r'\D', '', v_stripped[1:])
        # Basic validation: ensure there's something after '+'
        if not digits_after_plus:
             raise ValueError(f"Invalid phone number format (empty after '+'): {v}")
        return f"+{digits_after_plus}"
    # Fallback for other numeric inputs (might be international without '+')
    # This is less reliable - assumes user input a valid number without '+'
    elif digits.isdigit() and len(digits) > 0 :
        # You might want stricter validation here depending on your needs
        # Prepending '+' might be incorrect if it's not a +1 number.
        # Consider returning digits or raising error if format is ambiguous.
        # For now, returning digits prepended with '+' as a best guess.
        return f"+{digits}"
        
    # If the input doesn't resemble a phone number after cleaning
    raise ValueError(f"Invalid or unrecognized phone number format: {v}")


# --- Add these Tag schemas ---
class TagBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=100)]

class TagCreate(TagBase):
    pass

class TagRead(TagBase):
    id: int
    # business_id: int # Optional

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

    # Apply the validator using the function defined above
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
    twilio_number: Optional[str] = None # Assigned by system, not usually direct update
    business_phone_number: Optional[str] = None

    # Apply validators
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

    # Apply validator
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

    # Apply validator
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

    # Apply validator
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
    message: Annotated[str, StringConstraints(max_length=160)]
    send_time: Optional[str] = None # Consider using datetime

    @validator('message')
    def validate_message_length(cls, v):
        if len(v) > 160:
            raise ValueError("Message length exceeds 160 characters")
        return v

class SMSUpdate(BaseModel):
    updated_message: str
    status: str
    send_time: Optional[str] = None # Consider using datetime

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
    # Fields below are usually derived from analysis, not direct input for response training
    # tone: str
    # language_style: str
    # key_phrases: List[str]
    # formatting_preferences: Dict[str, Any]

class StyleAnalysis(BaseModel):
    key_phrases: List[str]
    style_notes: Dict[str, Any]
    personality_traits: List[str]
    message_patterns: Dict[str, Any]
    special_elements: Dict[str, Any]
    overall_summary: Optional[str] = None # Made optional

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
    smsTiming: str # Descriptive timing
    status: str
    send_datetime_utc: Optional[datetime] = None # Changed to datetime
    customer_timezone: Optional[str] = None

    class Config:
        orm_mode = True # Use orm_mode for SQLAlchemy models

class AllRoadmapMessagesResponse(BaseModel):
    total: int
    scheduledThisWeek: int
    messages: list[RoadmapMessageOut]

class ConversationMessage(BaseModel):
    id: str # Unique ID for frontend (e.g., "msg-123", "eng-cust-45")
    sender: Optional[str] = None # "customer", "ai", "owner" - Make Optional if not always applicable
    text: str
    timestamp: Optional[datetime] = None # Changed to datetime
    source: str # e.g., "ai_draft", "manual_reply", "scheduled_sms", "customer_reply"
    direction: Optional[str] = None # "incoming" or "outgoing" - Make Optional
    type: Optional[str] = None # Added for simpler frontend logic (e.g., 'customer', 'sent', 'ai_draft', 'scheduled')
    status: Optional[str] = None # Added status (e.g., 'sent', 'delivered', 'failed', 'pending_review')

class ConversationResponse(BaseModel):
    customer: dict # e.g., {"id": 1, "name": "Jane Doe", "phone": "+1..."}
    messages: List[ConversationMessage]

class ScheduledSMSOut(BaseModel):
    id: int
    customer_id: int
    business_id: int
    message: str # Changed from 'content' to 'message' for consistency? Check model.
    status: str
    send_time: datetime # Changed to datetime
    source: Optional[str] = None
    roadmap_id: Optional[int] = None
    is_hidden: bool
    business_timezone: str
    customer_timezone: Optional[str] = None

    class Config:
        orm_mode = True # Use orm_mode for SQLAlchemy models

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
    message_id: Optional[int] = None # Allow null if engagement starts with customer reply
    customer_id: int
    business_id: int
    response: Optional[str] = None # Customer's response (null if AI initiated)
    ai_response: Optional[str] = None # Business/AI response
    status: str = "pending_review" # Status of the AI response (pending, sent, etc.)
    parent_engagement_id: Optional[int] = None
    sent_at: Optional[datetime] = None # When the business/AI response was sent

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
    message_id: Optional[int] = None
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

# Scheduled SMS Schemas (Potentially redundant with Message model)
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
    method: str # e.g., "sms_double_optin", "manual_override"
    phone_number: str
    message_sid: Optional[str] = None
    status: str = "pending" # e.g., pending_confirmation, opted_in, opted_out, declined
    sent_at: Optional[datetime] = None # When the opt-in request was sent
    replied_at: Optional[datetime] = None # When the customer replied

    _normalize_consent_phone = validator('phone_number', pre=True, allow_reuse=True)(normalize_phone_number)

class ConsentLogCreate(ConsentLogBase):
    # Make sent_at truly optional or default to None, service will set it
    sent_at: Optional[datetime] = None


class ConsentLogUpdate(BaseModel):
    status: Optional[str] = None
    replied_at: Optional[datetime] = None

class ConsentLog(ConsentLogBase):
    id: int
    created_at: Optional[datetime] = None # Add if in model and needed
    updated_at: Optional[datetime] = None # Add if in model and needed

    class Config:
        from_attributes = True

class RoadmapMessageResponse(BaseModel):
    id: int
    customer_id: int
    business_id: int
    message: str = Field(..., alias='smsContent')
    scheduled_time: datetime = Field(..., alias='send_datetime_utc')
    status: str
    # relevance: Optional[str] = None # Aliases are optional here if names match model
    # success_indicator: Optional[str] = None
    # no_response_plan: Optional[str] = None
    # created_at: datetime
    # updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True # Important for aliases

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

# Consolidating ConsentBase, ensure only one definition is used
# class ConsentBase(BaseModel):
#     customer_id: int
#     business_id: int
#     phone_number: str
#     status: str = "awaiting_optin"
#     _normalize_consent_phone_2 = validator('phone_number', pre=True, allow_reuse=True)(normalize_phone_number)

class ConsentCreate(ConsentLogBase): # Inherit from the detailed ConsentLogBase
    pass

class ConsentResponse(ConsentLog): # Inherit from the detailed ConsentLog
    pass

class BusinessScenarioCreate(BaseModel):
    scenario: str = Field(..., description="The scenario description")
    context_type: str = Field(..., description="The type of context (e.g., inquiry, appreciation, follow_up)")
    # Fields below are typically outputs of analysis, not inputs for creation
    # key_phrases: Optional[List[str]] = Field(default=[])
    # style_notes: Optional[Dict[str, Any]] = Field(default={})
    # personality_traits: Optional[List[str]] = Field(default=[])
    # message_patterns: Optional[Dict[str, Any]] = Field(default={})
    # special_elements: Optional[Dict[str, Any]] = Field(default={})
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