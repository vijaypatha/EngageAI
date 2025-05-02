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
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Message as MessageModel
from app.schemas import Message, MessageCreate, MessageUpdate
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
):
    messages = db.query(MessageModel).offset(skip).limit(limit).all()
    return [Message.from_orm(message) for message in messages]

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