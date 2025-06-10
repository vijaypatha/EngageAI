# File: message_routes.py
# Link: /backend/app/routes/message_routes.py
#
# BUSINESS OWNER PERSPECTIVE:
# This file manages the core messaging functionality, providing the
# infrastructure for all communication between your business and customers. It handles the storage,
# retrieval, and management of all message types in your messaging ecosystem - from automated
# sequences to manual responses. These messages form the foundation of your customer engagement
# strategy, ensuring you maintain consistent and effective communication with your customers.
#
# DEVELOPER PERSPECTIVE:
# Routes:
# - POST / - Creates a new message in the system
# - GET / - Retrieves all messages with pagination
# - GET /{message_id} - Retrieves a specific message by ID
# - PUT /{message_id} - Updates an existing message
# - DELETE /{message_id} - Removes a message from the system
#
# Frontend Usage:
# - Messages are consumed by conversation views (frontend/src/app/inbox/[business_name]/page.tsx)
# - Used in customer conversations (frontend/src/app/conversations/[id]/page.tsx)
# - Referenced in engagement plans (frontend/src/app/contacts-ui/[id]/page.tsx)
# - Used in timeline previews (frontend/src/components/TimelinePreview.tsx)
#
# The Message model is a foundational entity representing all communication content.
# Each message belongs to a conversation and connects a business with a customer.
# Uses get_current_user auth dependency for authentication on create operations.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import Message as MessageModel
from app.schemas import (
    Message, MessageCreate, MessageUpdate,
    MessageSummarySchema, CustomerBasicInfo, BusinessBasicInfo # Import new schemas
)
from typing import List
from ..auth import get_current_user

router = APIRouter(
    tags=["messages"]
)

@router.post("/", response_model=Message)
def create_message(
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: Message = Depends(get_current_user)
):
    db_message = MessageModel(**message.model_dump())
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return Message.from_orm(db_message)

@router.get("/", response_model=List[Message])
def get_messages(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
    # current_user: Message = Depends(get_current_user) # Assuming you might want to filter by user's business
):
    messages_query = db.query(MessageModel)

    # Example: If you want to filter messages by the current user's business_id
    # This part depends on how `current_user` is structured and if it holds a business_id
    # For instance, if current_user is a User model that has a business_id:
    # if hasattr(current_user, 'business_id') and current_user.business_id:
    #     messages_query = messages_query.filter(MessageModel.business_id == current_user.business_id)
    # Or, if current_user *is* the BusinessProfile schema/model:
    # if current_user and hasattr(current_user, 'id'): # Assuming current_user here is a business profile
    # messages_query = messages_query.filter(MessageModel.business_id == current_user.id)


    messages = messages_query.options(
        joinedload(MessageModel.customer), # Assuming 'customer' is the relationship attribute name in MessageModel
        joinedload(MessageModel.business)  # Assuming 'business' is the relationship attribute name in MessageModel
    ).order_by(MessageModel.created_at.desc()).offset(skip).limit(limit).all() # Added order_by for consistency

    # The Message schema should have customer: Optional[CustomerSchema] and business: Optional[BusinessProfileSchema]
    # and Config.orm_mode = True for this to be automatically serialized.

    response_messages = []
    for msg_orm in messages:
        content_snippet = (
            (msg_orm.content[:100] + "...")
            if msg_orm.content and len(msg_orm.content) > 100
            else msg_orm.content
        )
        customer_info = CustomerBasicInfo.from_orm(msg_orm.customer) if msg_orm.customer else None
        business_info = BusinessBasicInfo.from_orm(msg_orm.business) if msg_orm.business else None

        # Manually construct the MessageSummarySchema to ensure correct field mapping
        # and inclusion of the snippet and basic infos.
        summary_data = {
            "id": msg_orm.id,
            "conversation_id": msg_orm.conversation_id, # Ensure this is part of MessageSummarySchema if needed
            "business_id": msg_orm.business_id,
            "customer_id": msg_orm.customer_id,
            "content_snippet": content_snippet,
            "message_type": msg_orm.message_type,
            "status": msg_orm.status,
            "created_at": msg_orm.created_at,
            "sent_at": msg_orm.sent_at,
            "customer": customer_info,
            "business": business_info,
        }
        response_messages.append(MessageSummarySchema(**summary_data))

    return response_messages

@router.get("/{message_id}", response_model=Message)
def get_message(message_id: int, db: Session = Depends(get_db)):
    message = db.query(MessageModel).filter(MessageModel.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return Message.from_orm(message)

@router.put("/{message_id}", response_model=Message)
def update_message(
    message_id: int,
    message: MessageUpdate,
    db: Session = Depends(get_db)
):
    db_message = db.query(MessageModel).filter(MessageModel.id == message_id).first()
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    for field, value in message.model_dump(exclude_unset=True).items():
        setattr(db_message, field, value)
    
    db.commit()
    db.refresh(db_message)
    return Message.from_orm(db_message)

@router.delete("/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db)):
    message = db.query(MessageModel).filter(MessageModel.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    db.delete(message)
    db.commit()
    return {"message": "Message deleted successfully"} 