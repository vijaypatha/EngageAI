# backend/app/schemas.py

from pydantic import BaseModel, constr, Field, field_validator, model_validator
from typing import Optional, Annotated, List, Dict, Any, Union, Literal
from pydantic import StringConstraints
import pytz
from datetime import datetime, timezone, date, time as TimeType
import uuid
import re
import enum
import logging
from enum import Enum

# Import the model enums used in schemas
from app.models import (
    MessageTypeEnum,
    MessageStatusEnum,
    OptInStatus,
    AppointmentRequestStatusEnum,
    AppointmentRequestSourceEnum,
    SenderTypeEnum
)

logger = logging.getLogger(__name__)

# --- APPOINTMENT RELATED SCHEMAS ---
class AppointmentIntent(str, enum.Enum):
    REQUEST_APPOINTMENT = "request_appointment"
    CONFIRMATION = "confirmation"
    CANCELLATION = "cancellation"
    RESCHEDULE = "reschedule"
    QUERY_AVAILABILITY = "query_availability"
    AMBIGUOUS_APPOINTMENT_RELATED = "ambiguous_appointment_related"
    NOT_APPOINTMENT = "not_appointment"
    ERROR_PARSING = "error_parsing"
    NEEDS_CLARIFICATION = "needs_clarification"
    OWNER_PROPOSAL = "owner_proposal"
    # Specific intents for AI draft generation for owner actions for the new endpoint
    OWNER_ACTION_CONFIRM = "owner_action_confirm"
    OWNER_ACTION_SUGGEST_RESCHEDULE = "owner_action_suggest_reschedule"
    OWNER_ACTION_DECLINE = "owner_action_decline"

class AppointmentTimePreference(BaseModel):
    datetime_str: Optional[str] = Field(None, description="The exact text snippet for date/time")
    start_time: Optional[datetime] = Field(None, description="Resolved start time in UTC")
    end_time: Optional[datetime] = Field(None, description="Resolved end time in UTC, if duration known")
    model_config = {'from_attributes': True, 'use_enum_values': True}

class AppointmentAIResponse(BaseModel):
    intent: AppointmentIntent
    datetime_preferences: List[AppointmentTimePreference] = Field(default_factory=list)
    parsed_intent_details: Optional[str] = None
    confidence_score: Optional[float] = None
    requires_clarification: bool = False
    clarification_question: Optional[str] = None
    failure_reason: Optional[str] = None
    model_config = {'from_attributes': True, 'use_enum_values': False}

# --- INBOX REPLY PAYLOAD SCHEMA ---
class InboxReplyPayload(BaseModel):
    message: str = Field(..., min_length=1)
    is_appointment_proposal: Optional[bool] = Field(default=False)
    model_config = {'extra': "forbid"}

# --- Helper Functions ---
def normalize_phone_number(v: Optional[str]) -> Optional[str]:
    if v is None: return None
    v_stripped = v.strip(); digits = re.sub(r'\D', '', v_stripped)
    if len(digits) == 10: return f"+1{digits}"
    if len(digits) == 11 and digits.startswith('1'): return f"+{digits}"
    if v_stripped.startswith('+'):
        digits_after_plus = re.sub(r'\D', '', v_stripped[1:])
        if not digits_after_plus: raise ValueError(f"Invalid phone (empty after '+'): {v}")
        return f"+{digits_after_plus}"
    if digits.isdigit() and len(digits) > 0 : return f"+{digits}"
    raise ValueError(f"Invalid phone format: {v}")

def validate_timezone_str(value: Optional[str]) -> Optional[str]:
    if value is None or value == "": return None
    try: pytz.timezone(value); return value
    except pytz.exceptions.UnknownTimeZoneError: raise ValueError(f"Invalid timezone: {value}")

# --- Tag Schemas ---
class TagBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=100)]
class TagCreate(TagBase): pass
class TagRead(TagBase):
    id: int
    model_config = {'from_attributes': True}

# --- Timezone Schemas ---
class TimezoneInfo(BaseModel):
    timezone: str; display_name: str; offset: str
    @field_validator('timezone', mode='before')
    @classmethod
    def validate_timezone_info_field(cls, v: str):
        validated = validate_timezone_str(v)
        if validated is None: raise ValueError("Timezone string cannot be empty for TimezoneInfo")
        return validated

# --- FAQ Schemas ---
class CustomFaqSchema(BaseModel):
    question: str; answer: str
    model_config = {'from_attributes': True}
class StructuredFaqDataSchema(BaseModel):
    operating_hours: Optional[str] = None; address: Optional[str] = None
    website: Optional[str] = None
    custom_faqs: Optional[List[CustomFaqSchema]] = Field(default_factory=list)
    model_config = {'from_attributes': True}

    # --- Availability Settings Schemas ---

AvailabilityStyleType = Literal["smart_hours", "flexible_coordinator", "manual_slots", ""]

class SmartHoursConfigSchema(BaseModel):
    weekdayStartTimeLocal: str = Field(..., description="HH:MM format")
    weekdayEndTimeLocal: str = Field(..., description="HH:MM format")
    exceptionsNote: Optional[str] = ""

    model_config = {'from_attributes': True}

class ManualRuleSchema(BaseModel):
    id: str
    dayOfWeek: str
    startTimeLocal: str # HH:MM
    endTimeLocal: str   # HH:MM
    isActive: bool
    isNew: Optional[bool] = None

    model_config = {'from_attributes': True}

class AvailabilitySettingsData(BaseModel): # THIS IS THE KEY SCHEMA FOR THE NEW ROUTE
    availabilityStyle: AvailabilityStyleType
    smartHoursConfig: Optional[SmartHoursConfigSchema] = None
    manualRules: Optional[List[ManualRuleSchema]] = Field(default_factory=list)

    model_config = {'from_attributes': True, 'use_enum_values': True}

# --- Business Schemas ---
class BusinessProfileBase(BaseModel):
    business_name: str; industry: str; business_goal: str
    primary_services: str; representative_name: str
    timezone: Optional[str] = "UTC"; business_phone_number: Optional[str] = None
    default_appointment_duration_minutes: Optional[int] = 15
    @field_validator('business_phone_number', mode='before')
    @classmethod
    def _normalize_bp_phone(cls, v: Optional[str]): return normalize_phone_number(v)
    @field_validator('timezone', mode='before')
    @classmethod
    def _validate_bp_base_tz(cls, v: Optional[str]): return validate_timezone_str(v)

class BusinessProfileCreate(BusinessProfileBase):
    twilio_number: Optional[str] = None; twilio_sid: Optional[str] = None
    messaging_service_sid: Optional[str] = None
    @field_validator('twilio_number', mode='before')
    @classmethod
    def _normalize_twilio_create_phone(cls, v: Optional[str]): return normalize_phone_number(v)

class BusinessProfileUpdate(BaseModel):
    business_name: Optional[str] = None; industry: Optional[str] = None; business_goal: Optional[str] = None
    primary_services: Optional[str] = None; representative_name: Optional[str] = None; timezone: Optional[str] = None
    twilio_number: Optional[str] = None; business_phone_number: Optional[str] = None
    notify_owner_on_reply_with_link: Optional[bool] = None; enable_ai_faq_auto_reply: Optional[bool] = None
    structured_faq_data: Optional[StructuredFaqDataSchema] = None
    default_appointment_duration_minutes: Optional[int] = None
    @field_validator('business_phone_number', mode='before')
    @classmethod
    def _normalize_bp_update_phone(cls, v: Optional[str]): return normalize_phone_number(v)
    @field_validator('twilio_number', mode='before')
    @classmethod
    def _normalize_twilio_update_phone(cls, v: Optional[str]): return normalize_phone_number(v)
    @field_validator('timezone', mode='before')
    @classmethod
    def _validate_bp_update_tz(cls, v: Optional[str]): return validate_timezone_str(v)
    model_config = {'from_attributes': True, 'extra': 'ignore', 'use_enum_values': True} # Ensure use_enum_values is here


class BusinessProfileRead(BusinessProfileBase):
    id: int
    twilio_number: Optional[str] = None; slug: Optional[str] = None
    created_at: datetime; updated_at: Optional[datetime] = None
    twilio_sid: Optional[str] = None; messaging_service_sid: Optional[str] = None
    notify_owner_on_reply_with_link: bool; enable_ai_faq_auto_reply: bool
    structured_faq_data: Optional[StructuredFaqDataSchema] = None
    @field_validator('twilio_number', mode='before')
    @classmethod
    def _normalize_bp_read_twilio_phone(cls, v: Optional[str]): return normalize_phone_number(v)
    model_config = {'from_attributes': True, 'use_enum_values': True}

class BusinessPhoneUpdate(BaseModel):
    business_phone_number: str
    @field_validator('business_phone_number', mode='before')
    @classmethod
    def _normalize_b_phone_update(cls, v: str): return normalize_phone_number(v)
    model_config = {'from_attributes': True}

# --- Customer Schemas ---
class CustomerBase(BaseModel):
    customer_name: Optional[str] = None; phone: str; business_id: int
    lifecycle_stage: Optional[str] = None; pain_points: Optional[str] = None
    interaction_history: Optional[str] = None; timezone: Optional[str] = None
    opted_in: Optional[bool] = Field(default=False)
    sms_opt_in_status: OptInStatus = OptInStatus.NOT_SET
    is_generating_roadmap: Optional[bool] = False; last_generation_attempt: Optional[datetime] = None
    @field_validator('phone', mode='before')
    @classmethod
    def _normalize_customer_phone(cls, v: Optional[str]): return normalize_phone_number(v)
    @field_validator('timezone', mode='before')
    @classmethod
    def _validate_cust_base_tz(cls, v: Optional[str]): return validate_timezone_str(v)

class CustomerCreate(CustomerBase): pass
class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = None; phone: Optional[str] = None
    lifecycle_stage: Optional[str] = None; pain_points: Optional[str] = None
    interaction_history: Optional[str] = None; timezone: Optional[str] = None
    opted_in: Optional[bool] = None; sms_opt_in_status: Optional[OptInStatus] = None
    tags: Optional[List[str]] = None
    @field_validator('phone', mode='before')
    @classmethod
    def _normalize_customer_phone_update(cls, v: Optional[str]): return normalize_phone_number(v)
    @field_validator('timezone', mode='before')
    @classmethod
    def _validate_cust_update_tz(cls, v: Optional[str]): return validate_timezone_str(v)
    model_config = {'extra': 'ignore'}

class CustomerRead(CustomerBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    latest_consent_status: Optional[OptInStatus] = None
    latest_consent_updated: Optional[datetime] = None
    tags: List[TagRead] = Field(default_factory=list)
    business: Optional[BusinessProfileRead] = None
    model_config = {'from_attributes': True, 'use_enum_values': True}


# --- Conversation & Message Schemas ---
class ConversationMessage(BaseModel):
    id: Union[int, str]
    content: str = Field(..., alias="text")
    message_type: MessageTypeEnum = Field(..., alias="type")
    status: Optional[MessageStatusEnum] = None
    direction: Optional[str] = None
    timestamp: datetime
    is_hidden: bool = False
    sender_name: Optional[str] = Field(None, alias="sender")
    source: Optional[str] = None
    model_config = {'from_attributes': True, 'populate_by_name': True, 'use_enum_values': True}

class ConversationResponseSchema(BaseModel):
    customer: CustomerRead
    messages: List[ConversationMessage]
    conversation_id: uuid.UUID
    latest_appointment_request: Optional["AppointmentRequestRead"] = None
    draft_reply_for_appointment: Optional[str] = None
    model_config = {'from_attributes': True, 'use_enum_values': True}

class AppointmentActionContextPayload(BaseModel):
    customer_name: Optional[str] = None
    original_customer_request_text: Optional[str] = None
    parsed_requested_time_text: Optional[str] = None
    owner_proposed_new_time_text: Optional[str] = Field(None, description="Full new time proposal from owner")
    owner_reason_for_action: Optional[str] = Field(None, description="Optional reason from owner")

class AppointmentActionDraftRequest(BaseModel):
    action_type: AppointmentIntent = Field(..., description="Specific owner action type.")
    context: Optional[AppointmentActionContextPayload] = Field(None, description="Context for AI.")
    model_config = {'use_enum_values': True}

class AppointmentActionDraftResponse(BaseModel):
    draft_message: str
    model_config = {'use_enum_values': True}

class ConversationBase(BaseModel):
    customer_id: int; business_id: int; status: str = "active"
class ConversationCreate(ConversationBase): pass
class ConversationUpdate(BaseModel): status: Optional[str] = None
class ConversationRead(ConversationBase):
    id: uuid.UUID; started_at: datetime; last_message_at: datetime
    customer: Optional[CustomerRead] = None
    model_config = {'from_attributes': True, 'use_enum_values': True}

class MessageBase(BaseModel):
    conversation_id: Optional[uuid.UUID] = None; business_id: int; customer_id: int
    content: str; message_type: MessageTypeEnum; status: MessageStatusEnum = MessageStatusEnum.PENDING
    sender_type: Optional[SenderTypeEnum] = None
    parent_id: Optional[int] = None; scheduled_send_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None; is_hidden: bool = False
    message_metadata: Optional[Dict[str,Any]] = None; twilio_message_sid: Optional[str] = None
    source: Optional[str] = None
    model_config = {'use_enum_values': True}

class MessageCreate(MessageBase): pass
class MessageUpdate(BaseModel):
    content: Optional[str] = None
    status: Optional[MessageStatusEnum] = None
    scheduled_send_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    is_hidden: Optional[bool] = None
    message_metadata: Optional[Dict[str,Any]] = None
    model_config = {'use_enum_values': True, 'extra': 'ignore'}

class MessageRead(MessageBase):
    id: int; created_at: datetime; updated_at: datetime
    model_config = {'from_attributes': True, 'use_enum_values': True}

class EngagementBase(BaseModel):
    message_id: Optional[int] = None; customer_id: int; business_id: int
    response: Optional[str] = None; ai_response: Optional[str] = None
    status: MessageStatusEnum = MessageStatusEnum.PENDING_REVIEW
    parent_engagement_id: Optional[int] = None; sent_at: Optional[datetime] = None
    is_hidden: Optional[bool] = False
    source: Optional[str] = None
    message_metadata: Optional[Dict[str, Any]] = None
    model_config = {'use_enum_values': True}

class EngagementCreate(EngagementBase): pass
class EngagementUpdate(BaseModel):
    ai_response: Optional[str] = None; status: Optional[MessageStatusEnum] = None
    sent_at: Optional[datetime] = None
    is_hidden: Optional[bool] = None
    model_config = {'use_enum_values': True, 'extra': 'ignore'}

class EngagementRead(EngagementBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    message: Optional[MessageRead] = None
    model_config = {'from_attributes': True, 'use_enum_values': True}

# --- ConsentLog Schemas ---
class ConsentLogBase(BaseModel):
    customer_id: int; business_id: int; method: str; phone_number: str
    message_sid: Optional[str] = None; status: OptInStatus = OptInStatus.PENDING
    sent_at: Optional[datetime] = None; replied_at: Optional[datetime] = None
    @field_validator('phone_number', mode='before')
    @classmethod
    def _normalize_consent_phone(cls, v: Optional[str]): return normalize_phone_number(v)
    model_config = {'use_enum_values': True}

class ConsentLogCreate(ConsentLogBase):
    sent_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))

class ConsentCreate(ConsentLogCreate): pass # Alias for route usage

class ConsentLogUpdate(BaseModel):
    status: Optional[OptInStatus] = None
    replied_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = {'use_enum_values': True, 'extra': 'ignore'}

class ConsentLogRead(ConsentLogBase):
    id: int; created_at: datetime; updated_at: datetime
    model_config = {'from_attributes': True, 'use_enum_values': True}

class ConsentResponse(ConsentLogRead): pass # Alias for route usage

# --- Roadmap Schemas ---
class RoadmapMessageBase(BaseModel):
    message_id: Optional[int] = None; customer_id: int; business_id: int
    smsContent: str; smsTiming: str; status: MessageStatusEnum = MessageStatusEnum.PENDING_REVIEW
    send_datetime_utc: Optional[datetime] = None
    relevance: Optional[str] = None; success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None
    model_config = {'use_enum_values': True}

class RoadmapMessageCreate(RoadmapMessageBase): pass
class RoadmapMessageUpdate(BaseModel):
    smsContent: Optional[str] = None; smsTiming: Optional[str] = None
    status: Optional[MessageStatusEnum] = None; send_datetime_utc: Optional[datetime] = None
    relevance: Optional[str] = None; success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None
    model_config = {'use_enum_values': True, 'extra': 'ignore'}

class RoadmapMessageRead(RoadmapMessageBase):
    id: int; customer_name: Optional[str] = None
    customer_timezone: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    model_config = {'from_attributes': True, 'use_enum_values': True}

class RoadmapGenerate(BaseModel):
    customer_id: int
    business_id: int
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context for roadmap generation.")
    model_config = {'from_attributes': True}

class RoadmapResponse(BaseModel):
    status: str
    message: Optional[str] = None
    roadmap: Optional[List[RoadmapMessageRead]] = Field(None, description="List of generated roadmap messages.")
    total_messages: Optional[int] = None
    customer_info: Optional[CustomerRead] = None
    business_info: Optional[BusinessProfileRead] = None
    model_config = {'from_attributes': True}

class RoadmapMessageResponse(BaseModel):
    id: int
    customer_id: int
    business_id: int
    message: str = Field(..., alias='smsContent')
    scheduled_time: datetime = Field(..., alias='send_datetime_utc')
    status: MessageStatusEnum
    relevance: Optional[str] = None
    success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None
    model_config = {'from_attributes': True, 'populate_by_name': True, 'use_enum_values': True}


# --- Twilio Schemas ---
class TwilioNumberAssign(BaseModel):
    business_id: int; phone_number: str
    @field_validator('phone_number', mode='before')
    @classmethod
    def _normalize_twilio_phone(cls, v: Optional[str]): return normalize_phone_number(v)

class TwilioSMSWebhookPayload(BaseModel):
    MessageSid: str; SmsSid: Optional[str] = None; AccountSid: str
    MessagingServiceSid: Optional[str] = None; From: str; To: str
    Body: Optional[str] = None; NumMedia: int = Field(default=0)
    FromCity: Optional[str] = None; FromState: Optional[str] = None; FromZip: Optional[str] = None; FromCountry: Optional[str] = None
    ToCity: Optional[str] = None; ToState: Optional[str] = None; ToZip: Optional[str] = None; ToCountry: Optional[str] = None
    @field_validator('From', mode='before')
    @classmethod
    def _normalize_from_phone(cls, v: Optional[str]): return normalize_phone_number(v)
    @field_validator('To', mode='before')
    @classmethod
    def _normalize_to_phone(cls, v: Optional[str]): return normalize_phone_number(v)


# --- Business Style/Scenario Schemas ---
class BusinessOwnerStyleBase(BaseModel):
    # business_id: int # Usually from path/auth, not in create/update body directly
    scenario: Optional[str] = None
    response: Optional[str] = None
    context_type: Optional[str] = None
    key_phrases: Optional[List[str]] = Field(default_factory=list)
    style_notes: Optional[Dict[str, Any]] = Field(default_factory=dict)
    personality_traits: Optional[List[str]] = Field(default_factory=list)
    message_patterns: Optional[Dict[str, Any]] = Field(default_factory=dict)
    special_elements: Optional[Dict[str, Any]] = Field(default_factory=dict)
    last_analyzed: Optional[datetime] = None

class BusinessOwnerStyleCreate(BusinessOwnerStyleBase):
    business_id: int # Required for creation if not from path
    pass

class BusinessOwnerStyleUpdate(BaseModel):
    scenario: Optional[str] = None
    response: Optional[str] = None
    context_type: Optional[str] = None
    key_phrases: Optional[List[str]] = None
    style_notes: Optional[Dict[str, Any]] = None
    personality_traits: Optional[List[str]] = None
    message_patterns: Optional[Dict[str, Any]] = None
    special_elements: Optional[Dict[str, Any]] = None
    model_config = {'extra': 'ignore'}

class BusinessOwnerStyleRead(BusinessOwnerStyleBase):
    id: int
    business_id: int
    model_config = {'from_attributes': True}

class SMSStyleInput(BaseModel):
    business_id: int
    scenario: str
    response: str
    context_type: str
    model_config = {'from_attributes': True}

class StyleAnalysis(BaseModel):
    key_phrases: List[str] = Field(default_factory=list)
    style_notes: Dict[str, Any] = Field(default_factory=dict)
    personality_traits: List[str] = Field(default_factory=list)
    message_patterns: Dict[str, Any] = Field(default_factory=dict)
    special_elements: Dict[str, Any] = Field(default_factory=dict)
    overall_summary: Optional[str] = None
    model_config = {'from_attributes': True}

class SMSStyleResponse(BaseModel):
    status: str
    message: Optional[str] = None
    updated_count: Optional[int] = None
    updated_styles: Optional[List[Dict[str, Any]]] = None
    style_analysis: Optional[StyleAnalysis] = None
    model_config = {'from_attributes': True}

class BusinessScenarioCreate(BaseModel):
    scenario: str = Field(...)
    context_type: str = Field(...)
    response: Optional[str] = Field(default="", description="Example response from business owner.")
    key_phrases: Optional[List[str]] = Field(default_factory=list)
    style_notes: Optional[Dict[str, Any]] = Field(default_factory=dict)
    personality_traits: Optional[List[str]] = Field(default_factory=list)
    message_patterns: Optional[Dict[str, Any]] = Field(default_factory=dict)
    special_elements: Optional[Dict[str, Any]] = Field(default_factory=dict)
    model_config = {'from_attributes': True}


# --- AppointmentAvailability Schemas ---
class AppointmentAvailabilityBase(BaseModel):
    day_of_week: str = Field(..., description="Day of the week, e.g., 'Monday'.")
    start_time_iso: str = Field(..., alias="start_time", description="Start datetime as ISO 8601 string with timezone offset, representing a recurring time (e.g., '1970-01-05T09:00:00-07:00').")
    end_time_iso: str = Field(..., alias="end_time", description="End datetime as ISO 8601 string, similar to start_time.")
    is_active: bool = True

    @field_validator('start_time_iso', 'end_time_iso', mode='before')
    @classmethod
    def validate_iso_format(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError("Time must be in valid ISO 8601 format (e.g., 'YYYY-MM-DDTHH:MM:SSZ' or 'YYYY-MM-DDTHH:MM:SS+/-HH:MM').")
        return v

    @model_validator(mode='after')
    def check_start_end_order(self) -> 'AppointmentAvailabilityBase':
        start_dt = datetime.fromisoformat(self.start_time_iso.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(self.end_time_iso.replace('Z', '+00:00'))
        if start_dt.time() >= end_dt.time():
            raise ValueError('End time must be after start time for a recurring availability slot.')
        return self
    model_config = {'populate_by_name': True, 'from_attributes': True, 'use_enum_values': True}

class AppointmentAvailabilityCreate(AppointmentAvailabilityBase):
    pass

class AppointmentAvailabilityRead(BaseModel):
    id: int
    business_id: int
    day_of_week: str
    start_time: datetime
    end_time: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {'from_attributes': True, 'use_enum_values': True}

class AppointmentAvailabilityUpdate(BaseModel):
    day_of_week: Optional[str] = None
    start_time_iso: Optional[str] = Field(None, alias="start_time")
    end_time_iso: Optional[str] = Field(None, alias="end_time")
    is_active: Optional[bool] = None

    @field_validator('start_time_iso', 'end_time_iso', mode='before')
    @classmethod
    def validate_iso_format_update(cls, v: Optional[str]) -> Optional[str]:
        if v is None: return None
        try: datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError: raise ValueError("Time must be in valid ISO 8601 format.")
        return v

    @model_validator(mode='after')
    def check_start_end_order_update(self) -> 'AppointmentAvailabilityUpdate':
        if self.start_time_iso and self.end_time_iso:
            start_dt = datetime.fromisoformat(self.start_time_iso.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(self.end_time_iso.replace('Z', '+00:00'))
            if start_dt.time() >= end_dt.time():
                raise ValueError('End time must be after start time if both are provided.')
        return self
    model_config = {'populate_by_name': True, 'from_attributes': True, 'use_enum_values': True, 'extra': 'ignore'}


# --- AppointmentRequest Schemas ---
class AppointmentRequestBase(BaseModel):
    business_id: int; customer_id: int
    customer_initiated_message_id: Optional[int] = None
    business_proposal_message_id: Optional[int] = None
    customer_reply_to_proposal_message_id: Optional[int] = None
    customer_reschedule_suggestion: Optional[str] = None
    original_message_text: Optional[str] = None; parsed_requested_time_text: Optional[str] = None
    parsed_requested_datetime_utc: Optional[datetime] = None
    status: AppointmentRequestStatusEnum; resolution_type: Optional[str] = None
    source: AppointmentRequestSourceEnum; ai_suggested_reply: Optional[str] = None
    confirmed_datetime_utc: Optional[datetime] = None
    owner_suggested_time_text: Optional[str] = None
    owner_suggested_datetime_utc: Optional[datetime] = None
    owner_actioned_at: Optional[datetime] = None; owner_removed_reason: Optional[str] = None
    details: Optional[str] = None
    model_config = {'from_attributes': True, 'use_enum_values': True}

class AppointmentRequestCreateInternal(AppointmentRequestBase): pass

class AppointmentRequestUpdate(BaseModel): # Generic update schema
    parsed_requested_time_text: Optional[str] = None
    parsed_requested_datetime_utc: Optional[datetime] = None
    status: Optional[AppointmentRequestStatusEnum] = None
    resolution_type: Optional[str] = None
    ai_suggested_reply: Optional[str] = None
    confirmed_datetime_utc: Optional[datetime] = None
    owner_suggested_time_text: Optional[str] = None
    owner_suggested_datetime_utc: Optional[datetime] = None
    owner_actioned_at: Optional[datetime] = None
    owner_removed_reason: Optional[str] = None
    details: Optional[str] = None
    customer_reschedule_suggestion: Optional[str] = None
    model_config = {'from_attributes': True, 'use_enum_values': True, 'extra': 'ignore'}

class AppointmentRequestRead(AppointmentRequestBase):
    id: int; created_at: datetime; updated_at: datetime
    business: Optional[BusinessProfileRead] = None
    customer: Optional[CustomerRead] = None
    customer_initiated_message_ref: Optional[MessageRead] = None
    business_proposal_message_ref: Optional[MessageRead] = None
    customer_reply_to_proposal_message_ref: Optional[MessageRead] = None
    model_config = {'from_attributes': True, 'use_enum_values': True}

class AppointmentRequestDashboardItem(BaseModel):
    id: int; customer_id: int; customer_name: Optional[str] = None; customer_phone: Optional[str] = None
    original_message_text: Optional[str] = None; parsed_requested_time_text: Optional[str] = None
    parsed_requested_datetime_utc: Optional[datetime] = None
    status: AppointmentRequestStatusEnum; source: AppointmentRequestSourceEnum
    confirmed_datetime_utc: Optional[datetime] = None
    owner_suggested_time_text: Optional[str] = None
    owner_suggested_datetime_utc: Optional[datetime] = None
    customer_reschedule_suggestion: Optional[str] = None; details: Optional[str] = None
    created_at: datetime; updated_at: datetime
    display_time_text: Optional[str] = None
    requested_datetime_utc_iso: Optional[str] = None
    model_config = {'from_attributes': True, 'use_enum_values': True}

class AppointmentRequestStatusUpdateByOwner(BaseModel):
    new_status: AppointmentRequestStatusEnum  # This should be the Enum type itself
    owner_notes: Optional[str] = None
    confirmed_datetime_utc: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    owner_suggested_datetime_utc: Optional[datetime] = None
    send_sms_to_customer: Optional[bool] = False # Default if not provided
    sms_message_body: Optional[str] = None


    @model_validator(mode='after')
    def check_payload_consistency(self) -> 'AppointmentRequestStatusUpdateByOwner':
        if self.new_status == AppointmentRequestStatusEnum.OWNER_PROPOSED_RESCHEDULE:
            if not self.owner_suggested_datetime_utc_iso:
                raise ValueError("OWNER_PROPOSED_RESCHEDULE requires 'owner_suggested_datetime_utc_iso'.")
            try:
                parsed_dt = datetime.fromisoformat(self.owner_suggested_datetime_utc_iso.replace('Z', '+00:00'))
                if parsed_dt.tzinfo is None or parsed_dt.tzinfo.utcoffset(parsed_dt) != timezone.utc.utcoffset(None):
                    raise ValueError("'owner_suggested_datetime_utc_iso' must be timezone-aware UTC.")
            except ValueError as e:
                raise ValueError(f"Invalid 'owner_suggested_datetime_utc_iso': {e}")
        if self.send_sms_to_customer and not self.sms_message_body:
            raise ValueError("If 'send_sms_to_customer' is true, 'sms_message_body' must be provided.")
        return self
        
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "new_status": "confirmed_by_owner",
                    "resolution_notes": "Customer called to confirm original request, looks good.",
                    "send_sms_to_customer": True,
                    "sms_message_body": "Great news! Your appointment for Tuesday at 4 PM is confirmed. We look forward to seeing you!"
                },
                {
                    "new_status": "owner_proposed_reschedule",
                    "owner_suggested_datetime_utc_iso": "2024-07-25T16:00:00Z",
                    "owner_suggested_time_text": "Thursday at 4 PM",
                    "resolution_notes": "Original time slot conflict with an urgent matter.",
                    "send_sms_to_customer": True,
                    "sms_message_body": "Regarding your appointment request, would Thursday at 4 PM work for you instead? Please let us know."
                },
                {
                    "new_status": "declined_by_owner",
                    "resolution_notes": "Unfortunately, we are fully booked for the requested period and cannot accommodate this request at the moment.",
                    "send_sms_to_customer": True,
                    "sms_message_body": "We appreciate you reaching out! Unfortunately, we are unable to accommodate your appointment request at this time. Please call us if you'd like to discuss other options."
                }
            ]
        },
        "use_enum_values": True,
        "extra": "ignore"
    }


# --- Instant Nudge Schema ---
class InstantNudgeSendPayload(BaseModel):
    customer_ids: List[int] = Field(..., description="List of customer IDs to send the nudge to.")
    message: str = Field(..., description="The content of the message to be sent.")
    business_id: int = Field(..., description="The ID of the business sending the nudge.")
    send_datetime_utc: Optional[datetime] = Field(None, description="Optional: UTC datetime to schedule the message. If None, send immediately.")
    is_appointment_proposal: bool = Field(False, description="Indicates if this nudge is an appointment proposal.")
    proposed_datetime_utc: Optional[datetime] = Field(None, description="Optional: UTC datetime for the proposed appointment, if is_appointment_proposal is true.")
    appointment_notes: Optional[str] = Field(None, description="Optional: Additional notes for the appointment proposal.")

    @field_validator("send_datetime_utc", mode='before')
    @classmethod
    def ensure_send_dt_aware_and_utc(cls, v: Optional[Union[str, datetime]]) -> Optional[datetime]:
        if v is None: return None
        parsed_dt: Optional[datetime] = None
        if isinstance(v, str):
            try: parsed_dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError: raise ValueError("Invalid ISO datetime for send_datetime_utc.")
        elif isinstance(v, datetime): parsed_dt = v
        else: raise ValueError("send_datetime_utc must be datetime string or object.")
        if parsed_dt.tzinfo is None or parsed_dt.tzinfo.utcoffset(parsed_dt) is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        else: parsed_dt = parsed_dt.astimezone(timezone.utc)
        return parsed_dt
    model_config = {'from_attributes': True, 'extra': "forbid", 'use_enum_values': True}


# --- Update Forward declaration ---
ConversationResponseSchema.model_rebuild()
CustomerRead.model_rebuild()
AppointmentRequestRead.model_rebuild()