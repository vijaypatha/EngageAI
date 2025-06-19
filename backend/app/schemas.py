# backend/app/schemas.py

from pydantic import BaseModel, constr, Field, validator, field_validator
from typing import Optional, Annotated, List, Dict, Any, Literal
from pydantic import StringConstraints
import pytz
from datetime import datetime
import uuid
import re

from app.models import MessageTypeEnum, MessageStatusEnum, OptInStatus, NudgeStatusEnum, NudgeTypeEnum

def normalize_phone_number(v: Optional[str]) -> Optional[str]:
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

def validate_timezone_str(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    try:
        pytz.timezone(value)
        return value
    except pytz.exceptions.UnknownTimeZoneError:
        raise ValueError(f"Invalid timezone: {value}")
    
class CustomerFindOrCreate(BaseModel):
    phone_number: str
    business_id: int
    customer_name: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    _normalize_phone = validator('phone_number', pre=True, allow_reuse=True)(normalize_phone_number)

class TagBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=100)]
class TagCreate(TagBase): pass
class TagRead(TagBase):
    id: int
    class Config: from_attributes = True

class TagAssociationRequest(BaseModel):
    tag_ids: List[int] = Field(..., description="List of Tag IDs to associate with the customer.")

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
    operating_hours: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    custom_faqs: Optional[List[CustomFaqSchema]] = Field(default_factory=list)
    class Config: from_attributes = True

class BusinessProfileBase(BaseModel):
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
    review_platform_url: Optional[str] = None
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
    class Config: from_attributes = True

class BusinessPhoneUpdate(BaseModel):
    business_phone_number: str
    _normalize_b_phone_update = validator('business_phone_number', pre=True, allow_reuse=True)(normalize_phone_number)
    class Config: from_attributes = True

class CustomerBase(BaseModel):
    customer_name: str
    phone: str
    lifecycle_stage: str
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

class SMSCreate(BaseModel):
    customer_id: int
    message: Annotated[str, StringConstraints(max_length=160)]
    send_time: Optional[datetime] = None
    @validator('message')
    def validate_message_length(cls, v_msg_len):
        if len(v_msg_len) > 160:
            raise ValueError("Message length exceeds 160 characters")
        return v_msg_len

class SMSUpdate(BaseModel):
    updated_message: Optional[str] = None
    status: Optional[MessageStatusEnum] = None
    send_time: Optional[datetime] = None

class SMSApproveOnly(BaseModel): status: MessageStatusEnum

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

class RoadmapMessageOut(BaseModel):
    id: int; customer_id: int; customer_name: Optional[str] = None
    smsContent: str; smsTiming: str;
    status: MessageStatusEnum
    send_datetime_utc: Optional[datetime] = None; customer_timezone: Optional[str] = None
    relevance: Optional[str] = None; success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None
    class Config: from_attributes = True

class AllRoadmapMessagesResponse(BaseModel):
    total: int; scheduledThisWeek: int; messages: List[RoadmapMessageOut]

class ConversationMessage(BaseModel):
    id: str; text: str; source: str
    sender: Optional[str] = None; timestamp: Optional[datetime] = None
    direction: Optional[str] = None;
    type: Optional[MessageTypeEnum] = None
    status: Optional[MessageStatusEnum] = None
    is_hidden: Optional[bool] = False
    class Config: from_attributes = True

class ConversationResponse(BaseModel):
    customer: dict; messages: List[ConversationMessage]

class ConversationBase(BaseModel):
    customer_id: int; business_id: int;
    status: str = "active"
class ConversationCreate(ConversationBase): pass
class ConversationUpdate(BaseModel):
    status: Optional[str] = None
class Conversation(ConversationBase):
    id: uuid.UUID; started_at: datetime; last_message_at: datetime
    class Config: from_attributes = True

class MessageBase(BaseModel):
    conversation_id: Optional[uuid.UUID] = None
    business_id: int; customer_id: int; content: str;
    message_type: MessageTypeEnum
    status: MessageStatusEnum = MessageStatusEnum.PENDING_REVIEW
    parent_id: Optional[int] = None
    scheduled_time: Optional[datetime] = None; sent_at: Optional[datetime] = None
    is_hidden: bool = False; message_metadata: Optional[Dict[str,Any]] = None
    customer: Optional["Customer"] = None
    business: Optional["BusinessProfile"] = None

class MessageCreate(MessageBase): pass
class MessageUpdate(BaseModel):
    content: Optional[str] = None;
    status: Optional[MessageStatusEnum] = None
    scheduled_time: Optional[datetime] = None; sent_at: Optional[datetime] = None
    is_hidden: Optional[bool] = None; message_metadata: Optional[Dict[str,Any]] = None

class Message(MessageBase):
    id: int; created_at: datetime
    class Config: from_attributes = True

class MessageResponse(MessageBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    class Config: from_attributes = True

class MessageCreateSchema(BaseModel):
    message: str = Field(..., description="The content of the message to be sent.")

# FIX: Added the missing ScheduleMessagePayload schema.
class ScheduleMessagePayload(BaseModel):
    """Defines the required data for scheduling a message."""
    message: str
    send_datetime_utc: datetime

class EngagementBase(BaseModel):
    message_id: Optional[int] = None; customer_id: int; business_id: int
    response: Optional[str] = None; ai_response: Optional[str] = None
    status: MessageStatusEnum = MessageStatusEnum.PENDING_REVIEW
    parent_engagement_id: Optional[int] = None
    sent_at: Optional[datetime] = None
class EngagementCreate(EngagementBase): pass
class EngagementUpdate(BaseModel):
    response: Optional[str] = None; ai_response: Optional[str] = None
    status: Optional[MessageStatusEnum] = None
    sent_at: Optional[datetime] = None
class Engagement(EngagementBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    class Config: from_attributes = True

class RoadmapMessageBase(BaseModel):
    message_id: Optional[int] = None; customer_id: int; business_id: int
    smsContent: str; smsTiming: str;
    status: MessageStatusEnum = MessageStatusEnum.PENDING_REVIEW
    send_datetime_utc: Optional[datetime] = None
    relevance: Optional[str] = None; success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None
class RoadmapMessageCreate(RoadmapMessageBase): pass
class RoadmapMessageUpdate(BaseModel):
    smsContent: Optional[str] = None; smsTiming: Optional[str] = None;
    status: Optional[MessageStatusEnum] = None
    send_datetime_utc: Optional[datetime] = None; relevance: Optional[str] = None
    success_indicator: Optional[str] = None; no_response_plan: Optional[str] = None
class RoadmapMessage(RoadmapMessageBase):
    id: int; created_at: datetime; updated_at: Optional[datetime] = None
    class Config: from_attributes = True

class EditedMessagePayload(BaseModel):
    roadmap_message_id: int = Field(..., description="The ID of the RoadmapMessage being updated.")
    content: str = Field(..., description="The final, edited content of the message.")
    send_datetime_utc: datetime = Field(..., description="The final, edited time to send the message in UTC.")

class ScheduleEditedRoadmapsRequest(BaseModel):
    edited_messages: List[EditedMessagePayload]

class ScheduledSMSBase(BaseModel):
    customer_id: int; business_id: int; message: str;
    status: MessageStatusEnum = MessageStatusEnum.SCHEDULED
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
    status: Optional[MessageStatusEnum] = None
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
    status: OptInStatus = OptInStatus.PENDING
    sent_at: Optional[datetime] = None; replied_at: Optional[datetime] = None
    _normalize_consent_phone = validator('phone_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)

class ConsentLogCreate(ConsentLogBase):
    sent_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
class ConsentLogUpdate(BaseModel):
    status: Optional[OptInStatus] = None
    replied_at: Optional[datetime] = None
class ConsentLog(ConsentLogBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    class Config: from_attributes = True

class ConsentCreate(ConsentLogBase): pass
class ConsentResponse(ConsentLog): pass

class RoadmapMessageResponse(BaseModel):
    id: int
    customer_id: int
    business_id: int
    message: str = Field(..., alias='smsContent')
    smsTiming: Optional[str] = None
    scheduled_time: datetime = Field(..., alias='send_datetime_utc')
    status: MessageStatusEnum
    relevance: Optional[str] = None
    success_indicator: Optional[str] = None
    no_response_plan: Optional[str] = None
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

class TwilioNumberAssign(BaseModel):
    business_id: int
    phone_number: str
    _normalize_twilio_phone = validator('phone_number', pre=True, allow_reuse=True, always=True)(normalize_phone_number)

class BusinessScenarioCreate(BaseModel):
    scenario: str = Field(..., description="The scenario description")
    context_type: str = Field(..., description="The type of context")
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

class CoPilotNudgeBase(BaseModel):
    business_id: int
    customer_id: Optional[int] = None
    nudge_type: NudgeTypeEnum
    status: NudgeStatusEnum = NudgeStatusEnum.ACTIVE
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
    customer_name: Optional[str] = None
    class Config:
        from_attributes = True

class DismissNudgePayload(BaseModel):
    reason: Optional[str] = None

class SentimentActionPayload(BaseModel):
    action_type: str

class ConfirmTimedCommitmentPayload(BaseModel):
    confirmed_datetime_utc: datetime
    confirmed_purpose: str = Field(..., min_length=1, max_length=500)
    class Config:
        from_attributes = True

class TargetedEventBase(BaseModel):
    business_id: int
    customer_id: int
    event_datetime_utc: datetime
    purpose: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_from_nudge_id: Optional[int] = None

class TargetedEventCreate(TargetedEventBase):
    pass

class TargetedEventRead(TargetedEventBase):
    id: int
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class PlanMessage(BaseModel):
    text: str = Field(..., min_length=1, description="The content of the SMS message.")
    send_datetime_utc: datetime = Field(..., description="The absolute UTC datetime to send the message.")

class ActivateEngagementPlanPayload(BaseModel):
    customer_id: int = Field(..., description="The ID of the customer this plan is for.")
    messages: List[PlanMessage] = Field(..., min_length=1, description="The list of messages to be scheduled as part of the plan.")

class InboxCustomerSummary(BaseModel):
    customer_id: int
    customer_name: str
    phone: Optional[str] = None
    opted_in: bool
    consent_status: str
    last_message_content: Optional[str] = None
    last_message_timestamp: Optional[datetime] = None
    unread_message_count: int = 0
    business_id: int
    class Config:
        from_attributes = True

class PaginatedInboxSummaries(BaseModel):
    items: List[InboxCustomerSummary]
    total: int
    page: int
    size: int
    pages: int

class CustomerSummarySchema(BaseModel):
    id: int
    customer_name: str
    phone: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    opted_in: bool = False
    latest_consent_status: Optional[str] = None
    latest_consent_updated: Optional[datetime] = None
    tags: List[TagRead] = Field(default_factory=list)
    business_id: int
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
    conversation_id: Optional[uuid.UUID] = None
    business_id: int
    customer_id: int
    content_snippet: Optional[str] = None
    message_type: Optional[MessageTypeEnum] = None
    status: Optional[MessageStatusEnum] = None
    created_at: datetime
    sent_at: Optional[datetime] = None
    customer: Optional[CustomerBasicInfo] = None
    business: Optional[BusinessBasicInfo] = None
    class Config:
        from_attributes = True

class ConversationMessageForTimeline(Message):
    pass

class CustomerConversation(BaseModel):
    customer_id: int
    messages: List[ConversationMessageForTimeline]
    class Config:
        from_attributes = True

class AutopilotMessage(BaseModel):
    id: int
    content: str
    status: str
    scheduled_time: datetime
    customer: CustomerBasicInfo
    class Config:
        from_attributes = True

class ApprovalQueueItem(BaseModel):
    id: int
    content: str
    status: MessageStatusEnum
    created_at: datetime
    customer: CustomerBasicInfo
    message_metadata: Optional[dict] = None
    class Config:
        from_attributes = True

class ApprovePayload(BaseModel):
    content: Optional[str] = None
    send_datetime_utc: Optional[datetime] = None

class BulkActionPayload(BaseModel):
    message_ids: List[int] = Field(..., description="A list of message IDs to apply the action to.")
    action: Literal['approve', 'reject'] = Field(..., description="The action to perform: 'approve' or 'reject'.")
    send_datetime_utc: Optional[datetime] = None

class ComposerRoadmapRequest(BaseModel):
    business_id: int = Field(..., description="The ID of the business for which to generate roadmaps.")
    topic: str = Field(..., description="A brief topic or goal for the roadmap generation, e.g., 'New Customer Welcome'.")
    customer_ids: Optional[List[int]] = Field(None, description="A specific list of customer IDs to target. Use this or filter_tags.")
    filter_tags: Optional[List[str]] = Field(None, description="A list of tag names to filter customers by. All tags must match. Use this or customer_ids.")

class ComposerRoadmapResponse(BaseModel):
    customer_id: int
    customer_name: str
    roadmap_messages: List[RoadmapMessageOut] = Field(default_factory=list, description="The list of AI-generated draft messages for this customer's roadmap.")

class BatchRoadmapResponse(BaseModel):
    status: str
    message: str
    generated_roadmaps: List[ComposerRoadmapResponse] = Field(default_factory=list)

Customer.update_forward_refs()
MessageBase.update_forward_refs()
