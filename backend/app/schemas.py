# backend/app/schemas.py

from pydantic import BaseModel, constr, Field, validator, field_validator
from typing import Optional, Annotated, List, Dict, Any
from pydantic import StringConstraints
import pytz
from datetime import datetime
import uuid
import re

# Import the new enums from app.models
from app.models import MessageTypeEnum, MessageStatusEnum, OptInStatus, NudgeStatusEnum, NudgeTypeEnum # OptInStatus is already used

# Helper function to normalize phone numbers (YOUR ORIGINAL FUNCTION)
def normalize_phone_number(v: Optional[str]) -> Optional[str]:
    # ... (your existing code) ...
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
    elif digits.isdigit() and len(digits) > 0 : # Ensure there are digits before adding '+'
        return f"+{digits}"
    raise ValueError(f"Invalid or unrecognized phone number format: {v}")


# --- STANDALONE TIMEZONE VALIDATION FUNCTION (Pydantic V2 compatible for reuse) ---
def validate_timezone_str(value: Optional[str]) -> Optional[str]:
    # ... (your existing code) ...
    if value is None or value == "": 
        return None 
    try:
        pytz.timezone(value) 
        return value
    except pytz.exceptions.UnknownTimeZoneError:
        raise ValueError(f"Invalid timezone: {value}")

# ... (TagBase, TagCreate, TagRead, TimezoneInfo, CustomFaqSchema, StructuredFaqDataSchema remain the same) ...

class TagBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=100)]
class TagCreate(TagBase): pass
class TagRead(TagBase):
    id: int
    class Config: from_attributes = True

class TimezoneInfo(BaseModel):
    timezone: str
    display_name: str
    offset: str
    @field_validator('timezone', mode='before') 
    @classmethod 
    def validate_timezone_info_field(cls, v_val: str) -> str: 
        return validate_timezone_str(v_val)

class CustomFaqSchema(BaseModel):
    question: str; answer: str
    class Config: from_attributes = True
class StructuredFaqDataSchema(BaseModel):
    operating_hours: Optional[str] = None; address: Optional[str] = None
    website: Optional[str] = None
    custom_faqs: Optional[List[CustomFaqSchema]] = Field(default_factory=list)
    class Config: from_attributes = True


# --- Business Schemas (No direct change needed for MessageTypeEnum/MessageStatusEnum) ---
class BusinessProfileBase(BaseModel):
    # ... (your existing code) ...
    business_name: str; industry: str; business_goal: str
    primary_services: str; representative_name: str
    timezone: Optional[str] = "UTC"
    business_phone_number: Optional[str] = None
    review_platform_url: Optional[str] = None 

    _normalize_bp_phone = validator('business_phone_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)
    @field_validator('timezone', mode='before') 
    @classmethod
    def _validate_bp_base_timezone(cls, v: Optional[str]):
        return validate_timezone_str(v)

class BusinessProfileCreate(BusinessProfileBase):
    # ... (your existing code) ...
    twilio_number: Optional[str] = None
    twilio_sid: Optional[str] = None
    messaging_service_sid: Optional[str] = None
    
class BusinessProfileUpdate(BaseModel):
    # ... (your existing code) ...
    business_name: Optional[str] = None; industry: Optional[str] = None
    business_goal: Optional[str] = None; primary_services: Optional[str] = None
    representative_name: Optional[str] = None; timezone: Optional[str] = None
    twilio_number: Optional[str] = None; business_phone_number: Optional[str] = None
    notify_owner_on_reply_with_link: Optional[bool] = None
    enable_ai_faq_auto_reply: Optional[bool] = None
    structured_faq_data: Optional[StructuredFaqDataSchema] = None
    review_platform_url: Optional[str] = None

    _normalize_bp_update_phone = validator('business_phone_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)
    _normalize_twilio_update_phone = validator('twilio_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number) # Added always=True
    @field_validator('timezone', mode='before')
    @classmethod
    def _validate_bp_update_timezone(cls, v: Optional[str]):
        return validate_timezone_str(v)
    class Config: from_attributes = True

class BusinessProfile(BusinessProfileBase):
    # ... (your existing code) ...
    id: int; twilio_number: Optional[str] = None; slug: Optional[str] = None
    created_at: datetime; updated_at: Optional[datetime] = None
    twilio_sid: Optional[str] = None; messaging_service_sid: Optional[str] = None
    notify_owner_on_reply_with_link: bool
    enable_ai_faq_auto_reply: bool
    structured_faq_data: Optional[StructuredFaqDataSchema] = None

    _normalize_bp_resp_twilio_phone = validator('twilio_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number) # Added always=True
    class Config: from_attributes = True

class BusinessPhoneUpdate(BaseModel):
    # ... (your existing code) ...
    business_phone_number: str
    _normalize_b_phone_update = validator('business_phone_number', pre=True, allow_reuse=True)(normalize_phone_number)
    class Config: from_attributes = True

# --- Customer Schemas (No direct change needed for MessageTypeEnum/MessageStatusEnum) ---
class CustomerBase(BaseModel):
    customer_name: str
    phone: str
    lifecycle_stage: str
    # MODIFICATION: Changed to Optional[str] to allow None values from the database
    pain_points: Optional[str] = None
    interaction_history: Optional[str] = None
    business_id: int
    timezone: Optional[str] = None
    opted_in: Optional[bool] = False 
    is_generating_roadmap: Optional[bool] = False
    last_generation_attempt: Optional[datetime] = None

    _normalize_customer_phone = validator('phone', pre=True, allow_reuse=True, always=True)(normalize_phone_number)
    @field_validator('timezone', mode='before')
    @classmethod
    def _validate_cust_base_timezone(cls, v: Optional[str]):
        return validate_timezone_str(v)

class CustomerCreate(CustomerBase): pass
class CustomerUpdate(BaseModel):
    # ... (your existing code) ...
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
    # ... (your existing code) ...
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    latest_consent_status: Optional[str] = None # This could use OptInStatus if you wish
    latest_consent_updated: Optional[datetime] = None
    tags: List[TagRead] = Field(default_factory=list)
    class Config: from_attributes = True


# --- SMS Schemas (Could use MessageStatusEnum if desired) ---
class SMSCreate(BaseModel):
    # ... (your existing code) ...
    customer_id: int
    message: Annotated[str, StringConstraints(max_length=160)] 
    send_time: Optional[datetime] = None 

    @validator('message') # Keep existing validator if it's Pydantic v1 style and working
    def validate_message_length(cls, v_msg_len):
        if len(v_msg_len) > 160:
            raise ValueError("Message length exceeds 160 characters")
        return v_msg_len

class SMSUpdate(BaseModel):
    # ... (your existing code) ...
    updated_message: Optional[str] = None 
    status: Optional[MessageStatusEnum] = None  # MODIFIED: Use Enum
    send_time: Optional[datetime] = None  

class SMSApproveOnly(BaseModel): status: MessageStatusEnum # MODIFIED: Use Enum

# ... (EngagementResponse, SMSStyleInput, StyleAnalysis, SMSStyleResponse remain the same) ...
class EngagementResponse(BaseModel):
    customer_id: int; response: str

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


# ... (RoadmapMessageOut, AllRoadmapMessagesResponse, ConversationMessage, ConversationResponse remain the same) ...
class RoadmapMessageOut(BaseModel):
    id: int; customer_id: int; customer_name: Optional[str] = None 
    smsContent: str; smsTiming: str; 
    status: MessageStatusEnum # MODIFIED: Use Enum (if it applies to roadmap message statuses)
    send_datetime_utc: Optional[datetime] = None; customer_timezone: Optional[str] = None
    relevance: Optional[str] = None; success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None
    class Config: from_attributes = True 

class AllRoadmapMessagesResponse(BaseModel):
    total: int; scheduledThisWeek: int; messages: List[RoadmapMessageOut] 

class ConversationMessage(BaseModel):
    id: str; text: str; source: str # Assuming id here is string like from frontend
    sender: Optional[str] = None; timestamp: Optional[datetime] = None
    direction: Optional[str] = None; 
    type: Optional[MessageTypeEnum] = None # MODIFIED: Use Enum
    status: Optional[MessageStatusEnum] = None # MODIFIED: Use Enum
    is_hidden: Optional[bool] = False
    class Config: from_attributes = True

class ConversationResponse(BaseModel):
    customer: dict; messages: List[ConversationMessage]

# --- Core DB Model Schemas ---
class ConversationBase(BaseModel):
    customer_id: int; business_id: int; 
    status: str = "active" # This status is likely simpler, might not need full MessageStatusEnum
class ConversationCreate(ConversationBase): pass
class ConversationUpdate(BaseModel): 
    status: Optional[str] = None
class Conversation(ConversationBase):
    id: uuid.UUID; started_at: datetime; last_message_at: datetime
    class Config: from_attributes = True

class MessageBase(BaseModel):
    conversation_id: Optional[uuid.UUID] = None 
    business_id: int; customer_id: int; content: str; 
    message_type: MessageTypeEnum # MODIFIED: Use Enum
    status: MessageStatusEnum = MessageStatusEnum.PENDING_REVIEW # MODIFIED: Use Enum
    parent_id: Optional[int] = None
    scheduled_time: Optional[datetime] = None; sent_at: Optional[datetime] = None
    is_hidden: bool = False; message_metadata: Optional[Dict[str,Any]] = None

    customer: Optional["Customer"] = None # Forward reference for Customer schema
    business: Optional["BusinessProfile"] = None # Forward reference for BusinessProfile schema

    # Ensure Config allows ORM mode if not already present at this level,
    # though Message and MessageResponse will have it.
    # class Config:
    #     from_attributes = True

class MessageCreate(MessageBase): pass
class MessageUpdate(BaseModel):
    content: Optional[str] = None; 
    status: Optional[MessageStatusEnum] = None # MODIFIED: Use Enum
    scheduled_time: Optional[datetime] = None; sent_at: Optional[datetime] = None
    is_hidden: Optional[bool] = None; message_metadata: Optional[Dict[str,Any]] = None

class Message(MessageBase):
    id: int; created_at: datetime
    # customer: Optional[Customer] = None # Already in MessageBase
    # business: Optional[BusinessProfile] = None # Already in MessageBase
    class Config: from_attributes = True

class MessageResponse(MessageBase): 
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    # customer: Optional[Customer] = None # Already in MessageBase
    # business: Optional[BusinessProfile] = None # Already in MessageBase
    class Config: from_attributes = True

class EngagementBase(BaseModel): 
    message_id: Optional[int] = None; customer_id: int; business_id: int
    response: Optional[str] = None; ai_response: Optional[str] = None
    status: MessageStatusEnum = MessageStatusEnum.PENDING_REVIEW # MODIFIED: Use Enum
    parent_engagement_id: Optional[int] = None
    sent_at: Optional[datetime] = None
class EngagementCreate(EngagementBase): pass
class EngagementUpdate(BaseModel): 
    response: Optional[str] = None; ai_response: Optional[str] = None
    status: Optional[MessageStatusEnum] = None # MODIFIED: Use Enum
    sent_at: Optional[datetime] = None
class Engagement(EngagementBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    class Config: from_attributes = True

class RoadmapMessageBase(BaseModel): 
    message_id: Optional[int] = None; customer_id: int; business_id: int
    smsContent: str; smsTiming: str; 
    status: MessageStatusEnum = MessageStatusEnum.PENDING_REVIEW # MODIFIED: Use Enum
    send_datetime_utc: Optional[datetime] = None
    relevance: Optional[str] = None; success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None
class RoadmapMessageCreate(RoadmapMessageBase): pass
class RoadmapMessageUpdate(BaseModel): 
    smsContent: Optional[str] = None; smsTiming: Optional[str] = None; 
    status: Optional[MessageStatusEnum] = None # MODIFIED: Use Enum
    send_datetime_utc: Optional[datetime] = None; relevance: Optional[str] = None
    success_indicator: Optional[str] = None; no_response_plan: Optional[str] = None
class RoadmapMessage(RoadmapMessageBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    class Config: from_attributes = True

class ScheduledSMSBase(BaseModel):
    customer_id: int; business_id: int; message: str; 
    status: MessageStatusEnum = MessageStatusEnum.SCHEDULED # MODIFIED: Use Enum
    send_time: datetime
    source: Optional[str] = None; roadmap_id: Optional[int] = None; is_hidden: bool = False
    business_timezone: str; customer_timezone: Optional[str] = None

    @field_validator('business_timezone', 'customer_timezone', mode='before')
    @classmethod
    def _validate_scheduled_sms_timezones(cls, v: Optional[str]):
        return validate_timezone_str(v) 

class ScheduledSMSCreate(ScheduledSMSBase): pass
class ScheduledSMSUpdate(BaseModel):
    message: Optional[str] = None; 
    status: Optional[MessageStatusEnum] = None # MODIFIED: Use Enum
    send_time: Optional[datetime] = None; is_hidden: Optional[bool] = None
class ScheduledSMSResponse(ScheduledSMSBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    class Config: from_attributes = True
class ScheduledSMSOut(ScheduledSMSBase): 
    id: int
    class Config: from_attributes = True

class ConsentLogBase(BaseModel):
    customer_id: int; business_id: int; method: str; phone_number: str
    message_sid: Optional[str] = None; 
    status: OptInStatus = OptInStatus.PENDING # MODIFIED: Use Enum
    sent_at: Optional[datetime] = None; replied_at: Optional[datetime] = None
    _normalize_consent_phone = validator('phone_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)

class ConsentLogCreate(ConsentLogBase): 
    sent_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
class ConsentLogUpdate(BaseModel): 
    status: Optional[OptInStatus] = None # MODIFIED: Use Enum
    replied_at: Optional[datetime] = None
class ConsentLog(ConsentLogBase): 
    id: int
    created_at: Optional[datetime] = None # Kept Optional as per your original
    updated_at: Optional[datetime] = None # Kept Optional as per your original
    class Config: from_attributes = True

class ConsentCreate(ConsentLogBase): pass
class ConsentResponse(ConsentLog): pass

class RoadmapMessageResponse(BaseModel): 
    id: int; customer_id: int; business_id: int
    message: str = Field(..., alias='smsContent')
    scheduled_time: datetime = Field(..., alias='send_datetime_utc')
    status: MessageStatusEnum # MODIFIED: Use Enum
    relevance: Optional[str] = None
    success_indicator: Optional[str] = None; no_response_plan: Optional[str] = None
    class Config: from_attributes = True; populate_by_name = True

class RoadmapGenerate(BaseModel): 
    customer_id: int; business_id: int
    context: Optional[Dict[str, Any]] = None

class RoadmapResponse(BaseModel): 
    status: str; message: Optional[str] = None
    roadmap: Optional[List[RoadmapMessageResponse]] = None
    total_messages: Optional[int] = None
    customer_info: Optional[Dict[str, Any]] = None; business_info: Optional[Dict[str, Any]] = None
    class Config: from_attributes = True

class TwilioNumberAssign(BaseModel):
    business_id: int; phone_number: str
    _normalize_twilio_phone = validator('phone_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)


class BusinessScenarioCreate(BaseModel):
    scenario: str = Field(..., description="The scenario description")
    context_type: str = Field(..., description="The type of context")
    response: Optional[str] = Field(default="", description="The response to the scenario")

class BusinessOwnerStyleResponse(BaseModel):
    id: int; business_id: int; scenario: str; response: str
    context_type: str; last_analyzed: Optional[datetime] = None
    class Config: from_attributes = True

# --- CoPilot Nudge Schemas --- (Renamed from AINudge)
class CoPilotNudgeBase(BaseModel):
    business_id: int
    customer_id: Optional[int] = None # Nudge might not always be customer-specific
    nudge_type: NudgeTypeEnum # Using the Enum directly
    status: NudgeStatusEnum = NudgeStatusEnum.ACTIVE # Default status
    message_snippet: Optional[str] = None
    ai_suggestion: Optional[str] = None
    ai_evidence_snippet: Optional[Dict[str, Any]] = None
    ai_suggestion_payload: Optional[Dict[str, Any]] = None

class CoPilotNudgeCreate(CoPilotNudgeBase):
    pass

class CoPilotNudgeRead(CoPilotNudgeBase):
    id: int
    created_at: datetime
    updated_at: datetime
    customer_name: Optional[str] = None # Will be populated in the route logic

    class Config:
        from_attributes = True # Pydantic v2 way to enable ORM mode

# --- Payload Schemas for Nudge Actions ---
class DismissNudgePayload(BaseModel):
    reason: Optional[str] = None

class SentimentActionPayload(BaseModel):
    action_type: str # e.g., "REQUEST_REVIEW"

class ConfirmTimedCommitmentPayload(BaseModel):
    # The owner confirms or provides the specific datetime for the event in UTC
    confirmed_datetime_utc: datetime 
    
    # The owner confirms or provides the purpose of the event
    confirmed_purpose: str = Field(..., min_length=1, max_length=500) # Purpose is required

    class Config:
        from_attributes = True # For Pydantic v2, if needed, though usually not for request bodies.

# --- TargetedEvent Schemas ---
class TargetedEventBase(BaseModel):
    business_id: int
    customer_id: int
    event_datetime_utc: datetime
    purpose: Optional[str] = None
    status: str 
    notes: Optional[str] = None
    created_from_nudge_id: Optional[int] = None

class TargetedEventCreate(TargetedEventBase): # For potential direct creation later
    pass

class TargetedEventRead(TargetedEventBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True # For Pydantic v2 ORM mode

# --- NEW SCHEMAS FOR STRATEGIC ENGAGEMENT PLANS (ITERATION 4) ---

# This schema defines a single message within an engagement plan payload
class PlanMessage(BaseModel):
    text: str = Field(..., min_length=1, description="The content of the SMS message.")
    send_datetime_utc: datetime = Field(..., description="The absolute UTC datetime to send the message.")

# This is the main payload for activating an AI-drafted engagement plan
class ActivateEngagementPlanPayload(BaseModel):
    customer_id: int = Field(..., description="The ID of the customer this plan is for.")
    messages: List[PlanMessage] = Field(..., min_length=1, description="The list of messages to be scheduled as part of the plan.")


# --- Inbox Schemas ---
class InboxCustomerSummary(BaseModel):
    customer_id: int
    customer_name: str
    phone: Optional[str] = None # Optional as it might not be strictly needed for summary
    opted_in: bool
    consent_status: str
    last_message_content: Optional[str] = None
    last_message_timestamp: Optional[datetime] = None
    unread_message_count: int = 0 # Default to 0, can be updated by a more complex query
    business_id: int

    class Config:
        from_attributes = True

class PaginatedInboxSummaries(BaseModel):
    items: List[InboxCustomerSummary]
    total: int
    page: int
    size: int
    pages: int

# --- Summary Schemas for Payload Reduction ---

class CustomerSummarySchema(BaseModel):
    id: int
    customer_name: str
    phone: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    opted_in: bool = False # Default to false if not available
    latest_consent_status: Optional[str] = None
    latest_consent_updated: Optional[datetime] = None
    tags: List[TagRead] = Field(default_factory=list)
    business_id: int # Added business_id as it's in CustomerBase

    class Config:
        from_attributes = True

class CustomerBasicInfo(BaseModel):
    id: int
    customer_name: Optional[str] = None
    class Config:
        from_attributes = True

class BusinessBasicInfo(BaseModel):
    id: int
    business_name: Optional[str] = None
    class Config:
        from_attributes = True

class MessageSummarySchema(BaseModel):
    id: int
    conversation_id: Optional[uuid.UUID] = None # Added conversation_id
    business_id: int
    customer_id: int
    content_snippet: Optional[str] = None
    message_type: Optional[MessageTypeEnum] = None # Use the enum
    status: Optional[MessageStatusEnum] = None     # Use the enum
    created_at: datetime
    sent_at: Optional[datetime] = None
    customer: Optional[CustomerBasicInfo] = None
    business: Optional[BusinessBasicInfo] = None

    class Config:
        from_attributes = True

# --- Customer Conversation Schemas ---
# Re-using the existing Message schema for individual messages in a conversation for now.
# If specific fields or formatting are needed for the timeline, a more specific schema can be created.
# For example, ConversationMessageForTimeline(Message) could be used and customized if needed.
class ConversationMessageForTimeline(Message): # This already inherits customer & business from MessageBase
    pass

class CustomerConversation(BaseModel):
    customer_id: int
    messages: List[ConversationMessageForTimeline]
    class Config:
        from_attributes = True

# Update forward references for all models that might have them
# This is good practice at the end of the schemas file.
Customer.update_forward_refs()
MessageBase.update_forward_refs() # MessageBase contains Optional["Customer"], Optional["BusinessProfile"]
# Add other .update_forward_refs() if other models use string forward references.
# For now, focusing on the ones modified or relevant to the new summary schemas.
