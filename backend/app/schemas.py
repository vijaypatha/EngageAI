from pydantic import BaseModel, constr, Field, EmailStr, validator
from typing import Optional, Annotated, List
import pytz

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
class BusinessProfileCreate(BaseModel):
    business_name: str
    industry: str
    business_goal: str
    primary_services: str
    representative_name: str
    timezone: Optional[str] = "UTC"

    @validator('timezone')
    def validate_timezone(cls, v):
        try:
            pytz.timezone(v)
            return v
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f"Invalid timezone: {v}")

class BusinessProfileUpdate(BaseModel):
    business_name: Optional[str] = None
    industry: Optional[str] = None
    business_goal: Optional[str] = None
    primary_services: Optional[str] = None
    representative_name: Optional[str] = None
    timezone: Optional[str] = None

    @validator('timezone')
    def validate_timezone(cls, v):
        if v is not None:
            try:
                pytz.timezone(v)
                return v
            except pytz.exceptions.UnknownTimeZoneError:
                raise ValueError(f"Invalid timezone: {v}")
        return v

### ✅ Customer Schemas
class CustomerCreate(BaseModel):
    customer_name: str
    phone: str = Field(..., pattern=r'^\+\d{10,15}$')  # ✅ clean, safe, VS Code approved
    lifecycle_stage: str
    pain_points: str
    interaction_history: str
    business_id: int
    timezone: Optional[str] = None

    @validator('timezone')
    def validate_timezone(cls, v):
        if v is not None:
            try:
                pytz.timezone(v)
                return v
            except pytz.exceptions.UnknownTimeZoneError:
                raise ValueError(f"Invalid timezone: {v}")
        return v

class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    pain_points: Optional[str] = None
    interaction_history: Optional[str] = None
    timezone: Optional[str] = None

    @validator('timezone')
    def validate_timezone(cls, v):
        if v is not None:
            try:
                pytz.timezone(v)
                return v
            except pytz.exceptions.UnknownTimeZoneError:
                raise ValueError(f"Invalid timezone: {v}")
        return v

### ✅ SMS Schemas
class SMSCreate(BaseModel):
    customer_id: int
    message: str
    send_time: Optional[str] = None  # ISO format datetime string in business timezone

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