# backend/app/schemas.py

from pydantic import BaseModel, constr, Field, validator, field_validator # Added field_validator
from typing import Optional, Annotated, List, Dict, Any
from pydantic import StringConstraints
import pytz
from datetime import datetime
import uuid
import re

# Helper function to normalize phone numbers (YOUR ORIGINAL FUNCTION)
# (Ensure this function does NOT take 'cls' as its first argument if it's standalone)
def normalize_phone_number(v: Optional[str]) -> Optional[str]: # REMOVED 'cls'
    if v is None:
        return None
    v_stripped = v.strip()
    digits = re.sub(r'\D', '', v_stripped)
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    elif v_stripped.startswith('+'):
        digits_after_plus = re.sub(r'\D', '', v_stripped[1:])
        if not digits_after_plus:
            raise ValueError(f"Invalid phone number format (empty after '+'): {v}")
        return f"+{digits_after_plus}"
    elif digits.isdigit() and len(digits) > 0 :
        return f"+{digits}"
    raise ValueError(f"Invalid or unrecognized phone number format: {v}")

# --- STANDALONE TIMEZONE VALIDATION FUNCTION (Pydantic V2 compatible for reuse) ---
def validate_timezone_str(value: Optional[str]) -> Optional[str]:
    if value is None or value == "": # Handle empty string or None
        return None # Default will be applied by Pydantic model if field has one
    try:
        pytz.timezone(value) # Check if it's a valid timezone
        return value
    except pytz.exceptions.UnknownTimeZoneError:
        raise ValueError(f"Invalid timezone: {value}")

# --- Tag Schemas (YOUR ORIGINAL) ---
class TagBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=100)]
class TagCreate(TagBase): pass
class TagRead(TagBase):
    id: int
    class Config: from_attributes = True

# --- Timezone Schemas (YOUR ORIGINAL - TimezoneInfo.validate_timezone is now specific to this model) ---
class TimezoneInfo(BaseModel):
    timezone: str
    display_name: str
    offset: str

    @field_validator('timezone', mode='before') # Pydantic V2 style
    @classmethod # Keep if you intend to use cls, otherwise remove if standalone logic is enough
    def validate_timezone_info_field(cls, v_val: str) -> str: # Ensure 'cls' is used if it's a class method
        return validate_timezone_str(v_val) # Use the standalone validator

# --- NEW SCHEMAS FOR AUTOPILOT FEATURES ---
class CustomFaqSchema(BaseModel):
    question: str; answer: str
    class Config: from_attributes = True
class StructuredFaqDataSchema(BaseModel):
    operating_hours: Optional[str] = None; address: Optional[str] = None
    website: Optional[str] = None
    custom_faqs: Optional[List[CustomFaqSchema]] = Field(default_factory=list)
    class Config: from_attributes = True

# --- Business Schemas (Adding Autopilot fields and using new timezone validator) ---
class BusinessProfileBase(BaseModel):
    business_name: str; industry: str; business_goal: str
    primary_services: str; representative_name: str
    timezone: Optional[str] = "UTC"
    business_phone_number: Optional[str] = None

    _normalize_bp_phone = validator('business_phone_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)
    @field_validator('timezone', mode='before') # Pydantic V2 style
    @classmethod
    def _validate_bp_base_timezone(cls, v: Optional[str]):
        return validate_timezone_str(v)

class BusinessProfileCreate(BusinessProfileBase):
    twilio_number: Optional[str] = None
    twilio_sid: Optional[str] = None
    messaging_service_sid: Optional[str] = None
    
class BusinessProfileUpdate(BaseModel):
    business_name: Optional[str] = None; industry: Optional[str] = None
    business_goal: Optional[str] = None; primary_services: Optional[str] = None
    representative_name: Optional[str] = None; timezone: Optional[str] = None
    twilio_number: Optional[str] = None; business_phone_number: Optional[str] = None
    notify_owner_on_reply_with_link: Optional[bool] = None
    enable_ai_faq_auto_reply: Optional[bool] = None
    structured_faq_data: Optional[StructuredFaqDataSchema] = None

    _normalize_bp_update_phone = validator('business_phone_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)
    _normalize_twilio_update_phone = validator('twilio_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)
    @field_validator('timezone', mode='before')
    @classmethod
    def _validate_bp_update_timezone(cls, v: Optional[str]):
        return validate_timezone_str(v)
    class Config: from_attributes = True

class BusinessProfile(BusinessProfileBase):
    id: int; twilio_number: Optional[str] = None; slug: Optional[str] = None
    created_at: datetime; updated_at: Optional[datetime] = None
    twilio_sid: Optional[str] = None; messaging_service_sid: Optional[str] = None
    notify_owner_on_reply_with_link: bool
    enable_ai_faq_auto_reply: bool
    structured_faq_data: Optional[StructuredFaqDataSchema] = None

    _normalize_bp_resp_twilio_phone = validator('twilio_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)
    # Timezone is validated in BusinessProfileBase
    class Config: from_attributes = True

class BusinessPhoneUpdate(BaseModel):
    business_phone_number: str
    _normalize_b_phone_update = validator('business_phone_number', pre=True, allow_reuse=True)(normalize_phone_number)
    class Config: from_attributes = True

# --- Customer Schemas (Using new timezone validator) ---
class CustomerBase(BaseModel):
    customer_name: str; phone: str; lifecycle_stage: str; pain_points: str
    interaction_history: str; business_id: int
    timezone: Optional[str] = None
    opted_in: Optional[bool] = False # Changed from None to False for a clearer default
    is_generating_roadmap: Optional[bool] = False
    last_generation_attempt: Optional[datetime] = None

    _normalize_customer_phone = validator('phone', pre=True, allow_reuse=True, always=True)(normalize_phone_number)
    @field_validator('timezone', mode='before')
    @classmethod
    def _validate_cust_base_timezone(cls, v: Optional[str]):
        return validate_timezone_str(v)

class CustomerCreate(CustomerBase): pass
class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = None; phone: Optional[str] = None
    lifecycle_stage: Optional[str] = None; pain_points: Optional[str] = None
    interaction_history: Optional[str] = None; timezone: Optional[str] = None
    opted_in: Optional[bool] = None

    _normalize_customer_phone_update = validator('phone', pre=True, allow_reuse=True, always=True)(normalize_phone_number)
    @field_validator('timezone', mode='before')
    @classmethod
    def _validate_cust_update_timezone(cls, v: Optional[str]):
        return validate_timezone_str(v)

class Customer(CustomerBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    latest_consent_status: Optional[str] = None
    latest_consent_updated: Optional[datetime] = None
    tags: List[TagRead] = Field(default_factory=list)
    class Config: from_attributes = True


# --- SMS Schemas (YOUR ORIGINAL, ensure datetime types for send_time) ---
class SMSCreate(BaseModel):
    customer_id: int
    message: Annotated[str, StringConstraints(max_length=160)] # Your original used 160
    send_time: Optional[datetime] = None # Changed from str to datetime

    @validator('message')
    def validate_message_length(cls, v_msg_len):
        if len(v_msg_len) > 160: # Your original limit
            raise ValueError("Message length exceeds 160 characters")
        return v_msg_len

class SMSUpdate(BaseModel):
    updated_message: Optional[str] = None # Made Optional
    status: Optional[str] = None          # Made Optional
    send_time: Optional[datetime] = None  # Changed from str to datetime

class SMSApproveOnly(BaseModel): status: str


# --- Engagement Schema (YOUR ORIGINAL EngagementResponse) ---
class EngagementResponse(BaseModel):
    customer_id: int; response: str


# --- SMS Style Schemas (YOUR ORIGINAL) ---
class SMSStyleInput(BaseModel):
    business_id: int; scenario: str; response: str; context_type: str
class StyleAnalysis(BaseModel):
    key_phrases: List[str] = Field(default_factory=list); style_notes: Dict[str, Any] = Field(default_factory=dict)
    personality_traits: List[str] = Field(default_factory=list); message_patterns: Dict[str, Any] = Field(default_factory=dict)
    special_elements: Dict[str, Any] = Field(default_factory=dict); overall_summary: Optional[str] = None
class SMSStyleResponse(BaseModel):
    status: str; message: Optional[str] = None; updated_count: Optional[int] = None
    updated_styles: Optional[List[Dict[str, Any]]] = None; style_analysis: Optional[StyleAnalysis] = None
    class Config: from_attributes = True


# --- RoadmapMessageOut, AllRoadmapMessagesResponse, ConversationMessage, ConversationResponse (YOUR ORIGINAL) ---
class RoadmapMessageOut(BaseModel):
    id: int; customer_id: int; customer_name: Optional[str] = None # Was str, made Optional
    smsContent: str; smsTiming: str; status: str
    send_datetime_utc: Optional[datetime] = None; customer_timezone: Optional[str] = None
    relevance: Optional[str] = None; success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None
    class Config: from_attributes = True # Changed from orm_mode

class AllRoadmapMessagesResponse(BaseModel):
    total: int; scheduledThisWeek: int; messages: List[RoadmapMessageOut] # list to List

class ConversationMessage(BaseModel):
    id: str; text: str; source: str
    sender: Optional[str] = None; timestamp: Optional[datetime] = None
    direction: Optional[str] = None; type: Optional[str] = None; status: Optional[str] = None
    is_hidden: Optional[bool] = False
    class Config: from_attributes = True

class ConversationResponse(BaseModel):
    customer: dict; messages: List[ConversationMessage]


# --- Core DB Model Schemas (YOUR ORIGINAL NAMES, ensure they exist for imports) ---
class ConversationBase(BaseModel):
    customer_id: int; business_id: int; status: str = "active"
class ConversationCreate(ConversationBase): pass
class ConversationUpdate(BaseModel): # This is what conversation_routes.py needs
    status: Optional[str] = None
class Conversation(ConversationBase):
    id: uuid.UUID; started_at: datetime; last_message_at: datetime
    class Config: from_attributes = True

class MessageBase(BaseModel):
    conversation_id: Optional[uuid.UUID] = None # Was uuid.UUID, made Optional
    business_id: int; customer_id: int; content: str; message_type: str
    status: str = "pending_review"; parent_id: Optional[int] = None
    scheduled_time: Optional[datetime] = None; sent_at: Optional[datetime] = None
    is_hidden: bool = False; message_metadata: Optional[Dict[str,Any]] = None
class MessageCreate(MessageBase): pass
class MessageUpdate(BaseModel):
    content: Optional[str] = None; status: Optional[str] = None
    scheduled_time: Optional[datetime] = None; sent_at: Optional[datetime] = None
    is_hidden: Optional[bool] = None; message_metadata: Optional[Dict[str,Any]] = None
class Message(MessageBase):
    id: int; created_at: datetime
    class Config: from_attributes = True
class MessageResponse(MessageBase): # YOUR ORIGINAL
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    class Config: from_attributes = True

class EngagementBase(BaseModel): # YOUR ORIGINAL
    message_id: Optional[int] = None; customer_id: int; business_id: int
    response: Optional[str] = None; ai_response: Optional[str] = None
    status: str = "pending_review"; parent_engagement_id: Optional[int] = None
    sent_at: Optional[datetime] = None
class EngagementCreate(EngagementBase): pass
class EngagementUpdate(BaseModel): # YOUR ORIGINAL
    response: Optional[str] = None; ai_response: Optional[str] = None
    status: Optional[str] = None; sent_at: Optional[datetime] = None
class Engagement(EngagementBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    class Config: from_attributes = True

class RoadmapMessageBase(BaseModel): # YOUR ORIGINAL
    message_id: Optional[int] = None; customer_id: int; business_id: int
    smsContent: str; smsTiming: str; status: str = "pending_review"
    send_datetime_utc: Optional[datetime] = None
    relevance: Optional[str] = None; success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None
class RoadmapMessageCreate(RoadmapMessageBase): pass
class RoadmapMessageUpdate(BaseModel): # YOUR ORIGINAL
    smsContent: Optional[str] = None; smsTiming: Optional[str] = None; status: Optional[str] = None
    send_datetime_utc: Optional[datetime] = None; relevance: Optional[str] = None
    success_indicator: Optional[str] = None; no_response_plan: Optional[str] = None
class RoadmapMessage(RoadmapMessageBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    class Config: from_attributes = True

# --- ScheduledSMS Schemas (YOUR ORIGINAL, ensure ScheduledSMSOut is what message_workflow_routes needs) ---
class ScheduledSMSBase(BaseModel):
    customer_id: int; business_id: int; message: str; status: str = "scheduled"; send_time: datetime
    source: Optional[str] = None; roadmap_id: Optional[int] = None; is_hidden: bool = False
    business_timezone: str; customer_timezone: Optional[str] = None

    @field_validator('business_timezone', 'customer_timezone', mode='before')
    @classmethod
    def _validate_scheduled_sms_timezones(cls, v: Optional[str]):
        return validate_timezone_str(v) # Use the standalone validator

class ScheduledSMSCreate(ScheduledSMSBase): pass
class ScheduledSMSUpdate(BaseModel):
    message: Optional[str] = None; status: Optional[str] = None
    send_time: Optional[datetime] = None; is_hidden: Optional[bool] = None
class ScheduledSMSResponse(ScheduledSMSBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    class Config: from_attributes = True
class ScheduledSMSOut(ScheduledSMSBase): # THIS IS WHAT message_workflow_routes.py IMPORTS
    id: int
    # Other fields are inherited from ScheduledSMSBase. If created_at/updated_at are needed, add them.
    # Your original ScheduledSMSOut did not have created_at/updated_at.
    class Config: from_attributes = True


# --- ConsentLog Schemas (YOUR ORIGINAL) ---
class ConsentLogBase(BaseModel):
    customer_id: int; business_id: int; method: str; phone_number: str
    message_sid: Optional[str] = None; status: str = "pending"
    sent_at: Optional[datetime] = None; replied_at: Optional[datetime] = None
    _normalize_consent_phone = validator('phone_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)

class ConsentLogCreate(ConsentLogBase): # YOUR ORIGINAL
    sent_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

class ConsentLogUpdate(BaseModel): # YOUR ORIGINAL
    status: Optional[str] = None; replied_at: Optional[datetime] = None

class ConsentLog(ConsentLogBase): # YOUR ORIGINAL
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    class Config: from_attributes = True


# --- API Schemas for consent_routes.py (YOUR ORIGINAL NAMES) ---
class ConsentCreate(ConsentLogBase): # YOUR ORIGINAL
    # Based on your original, consent_routes.py expects ConsentCreate to be based on ConsentLogBase.
    # If the actual API payload for creation is simpler (e.g., just customer_id, business_id, phone_number),
    # this should be a distinct BaseModel with only those fields.
    # For now, assuming your original definition based on ConsentLogBase is what you want.
    pass

class ConsentResponse(ConsentLog): # YOUR ORIGINAL
    pass


# --- Schemas for AI Roadmap Generation API (YOUR ORIGINAL NAMES) ---
class RoadmapMessageResponse(BaseModel): # YOUR ORIGINAL NAME
    id: int; customer_id: int; business_id: int
    message: str = Field(..., alias='smsContent')
    scheduled_time: datetime = Field(..., alias='send_datetime_utc')
    status: str; relevance: Optional[str] = None
    success_indicator: Optional[str] = None; no_response_plan: Optional[str] = None
    class Config: from_attributes = True; populate_by_name = True

class RoadmapGenerate(BaseModel): # YOUR ORIGINAL NAME
    customer_id: int; business_id: int
    context: Optional[Dict[str, Any]] = None

class RoadmapResponse(BaseModel): # YOUR ORIGINAL NAME
    status: str; message: Optional[str] = None
    roadmap: Optional[List[RoadmapMessageResponse]] = None
    total_messages: Optional[int] = None
    customer_info: Optional[Dict[str, Any]] = None; business_info: Optional[Dict[str, Any]] = None
    class Config: from_attributes = True


# --- Twilio Schemas (YOUR ORIGINAL) ---
class TwilioNumberAssign(BaseModel):
    business_id: int; phone_number: str
    _normalize_twilio_phone = validator('phone_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)


# --- Business Scenario/Style Schemas (YOUR ORIGINAL) ---
class BusinessScenarioCreate(BaseModel):
    scenario: str = Field(..., description="The scenario description")
    context_type: str = Field(..., description="The type of context")
    response: Optional[str] = Field(default="", description="The response to the scenario")

class BusinessOwnerStyleResponse(BaseModel):
    id: int; business_id: int; scenario: str; response: str
    context_type: str; last_analyzed: Optional[datetime] = None
    class Config: from_attributes = True