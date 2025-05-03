from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
from pydantic import BaseModel
from app.database import get_db
from app.models import Engagement, Customer, Message, BusinessProfile, Conversation as ConversationModel
from app.celery_tasks import schedule_sms_task
import uuid
import pytz
from app.schemas import Conversation, ConversationCreate, ConversationUpdate
from typing import List
from ..auth import get_current_user


router = APIRouter(tags=["Conversations"])

# -------------------------------
# GET inbox summary: all customers with conversations
# -------------------------------
@router.get("/inbox")
def get_open_conversations(business_name: str = Query(...), db: Session = Depends(get_db)):
    business = db.query(BusinessProfile).filter(BusinessProfile.business_name == business_name).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    customers = db.query(Customer).filter(Customer.business_id == business.id).all()
    result = []

    for customer in customers:
        last_engagement = (
            db.query(Engagement)
            .filter(Engagement.customer_id == customer.id)
            .order_by(Engagement.sent_at.desc())
            .first()
        )
        if last_engagement:
            result.append({
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "last_message": last_engagement.response or last_engagement.ai_response,
                "status": "pending_review" if last_engagement.response and not last_engagement.ai_response else "replied",
                "timestamp": last_engagement.sent_at.isoformat() if last_engagement.sent_at else None,
            })

    # Sort by most recent
    result.sort(key=lambda x: x["timestamp"] or "", reverse=True)

    return {"conversations": result}

# -------------------------------
# GET full chat history for a specific customer
# -------------------------------
@router.get("/customer/{customer_id}")
def get_conversation(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    engagements = db.query(Engagement)\
        .filter(Engagement.customer_id == customer_id)\
        .all()

    messages = db.query(Message)\
        .filter(
            Message.customer_id == customer_id,
            Message.message_type == 'scheduled'
        )\
        .all()

    conversation = []
    utc = pytz.UTC

    for msg in engagements:
        if msg.response:
            conversation.append({
                "id": msg.id,
                "type": "customer",
                "text": msg.response,
                "timestamp": msg.sent_at.astimezone(utc) if msg.sent_at else None,
                "source": "customer_reply",
            })
        if msg.ai_response and msg.status != "sent":
            conversation.append({
                "id": msg.id,
                "type": "ai_draft",
                "text": msg.ai_response,
                "timestamp": None,
                "source": "ai_draft",
            })
        if msg.ai_response and msg.status == "sent":
            conversation.append({
                "id": msg.id,
                "type": "sent",
                "text": msg.ai_response,
                "timestamp": msg.sent_at.astimezone(utc) if msg.sent_at else None,
                "source": "manual_reply",
            })

    for msg in messages:
        # Handle message_metadata safely
        source = 'scheduled'
        if msg.message_metadata:
            try:
                metadata_dict = msg.message_metadata if isinstance(msg.message_metadata, dict) else {}
                source = metadata_dict.get('source', 'scheduled')
            except:
                source = 'scheduled'

        conversation.append({
            "sender": "owner",
            "text": msg.content,
            "timestamp": msg.scheduled_time.astimezone(utc) if msg.scheduled_time else None,
            "source": source,
            "direction": "outgoing"
        })

    # Sort with a key function that handles None values
    def get_sort_key(item):
        timestamp = item.get("timestamp")
        if timestamp is None:
            return datetime.min.replace(tzinfo=utc)
        return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=utc)

    sorted_conversation = sorted(
        conversation,
        key=get_sort_key
    )

    return {
        "customer": {
            "id": customer.id,
            "name": customer.customer_name
        },
        "messages": sorted_conversation
    }

# -------------------------------
# POST a manual reply from the business owner
# -------------------------------
class ManualReplyInput(BaseModel):
    message: str

@router.post("/customer/{customer_id}/reply")
def send_manual_reply(customer_id: int, payload: ManualReplyInput, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now = datetime.now(pytz.UTC)

    # Get or create conversation
    conversation = db.query(ConversationModel).filter(
        ConversationModel.customer_id == customer.id,
        ConversationModel.business_id == customer.business_id,
        ConversationModel.status == 'active'
    ).first()
    
    if not conversation:
        conversation = ConversationModel(
            id=uuid.uuid4(),
            customer_id=customer.id,
            business_id=customer.business_id,
            started_at=now,
            last_message_at=now,
            status='active'
        )
        db.add(conversation)
        db.flush()

    # Create message for SMS delivery
    message = Message(
        conversation_id=conversation.id,
        customer_id=customer.id,
        business_id=customer.business_id,
        content=payload.message,
        message_type='scheduled',
        status="scheduled",
        scheduled_time=now,
        message_metadata={
            'source': 'manual_reply'
        }
    )
    db.add(message)

    # Save to Engagements (for conversation history)
    new_msg = Engagement(
        customer_id=customer.id,
        message_id=message.id,
        response=None,
        ai_response=payload.message,
        status="sent",
        sent_at=now,
    )
    db.add(new_msg)

    # Commit and trigger Celery task
    db.commit()
    schedule_sms_task.delay(message.id)

    return {"status": "success", "message": "Reply sent and scheduled", "message_id": message.id}

@router.post("/", response_model=Conversation)
def create_conversation(
    conversation: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: Conversation = Depends(get_current_user)
):
    db_conversation = ConversationModel(**conversation.model_dump())
    db.add(db_conversation)
    db.commit()
    db.refresh(db_conversation)
    return Conversation.from_orm(db_conversation)

@router.get("/", response_model=List[Conversation])
def get_conversations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    conversations = db.query(ConversationModel).offset(skip).limit(limit).all()
    return [Conversation.from_orm(conversation) for conversation in conversations]

@router.get("/{conversation_id}", response_model=Conversation)
def get_conversation(conversation_id: int, db: Session = Depends(get_db)):
    conversation = db.query(ConversationModel).filter(ConversationModel.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return Conversation.from_orm(conversation)

@router.put("/{conversation_id}", response_model=Conversation)
def update_conversation(
    conversation_id: int,
    conversation: ConversationUpdate,
    db: Session = Depends(get_db)
):
    db_conversation = db.query(ConversationModel).filter(ConversationModel.id == conversation_id).first()
    if not db_conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    for field, value in conversation.model_dump(exclude_unset=True).items():
        setattr(db_conversation, field, value)
    
    db.commit()
    db.refresh(db_conversation)
    return Conversation.from_orm(db_conversation)

@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)):
    conversation = db.query(ConversationModel).filter(ConversationModel.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    db.delete(conversation)
    db.commit()
    return {"message": "Conversation deleted successfully"}