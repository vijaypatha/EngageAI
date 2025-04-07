from pydantic import BaseModel, constr, Field, EmailStr
from typing import Optional, Annotated

### ✅ Business Schemas
class BusinessProfileCreate(BaseModel):
    business_name: str
    industry: str
    business_goal: str
    primary_services: str
    representative_name: str
    

class BusinessProfileUpdate(BaseModel):
    business_name: Optional[str] = None
    industry: Optional[str] = None
    business_goal: Optional[str] = None
    primary_services: Optional[str] = None
    representative_name: Optional[str] = None
   

### ✅ Customer Schemas
class CustomerCreate(BaseModel):
    customer_name: str
    phone: str = Field(..., pattern=r'^\+\d{10,15}$')  # ✅ clean, safe, VS Code approved
    lifecycle_stage: str
    pain_points: str
    interaction_history: str




class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    pain_points: Optional[str] = None
    interaction_history: Optional[str] = None

### ✅ SMS Schemas
class SMSCreate(BaseModel):
    customer_id: int
    message: str

class SMSUpdate(BaseModel):
    updated_message: str
    status: str

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

    class Config:
        orm_mode = True

class AllRoadmapMessagesResponse(BaseModel):
    total: int
    scheduledThisWeek: int
    messages: list[RoadmapMessageOut]
    
    