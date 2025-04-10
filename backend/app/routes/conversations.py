from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from app.database import get_db
from app.models import Engagement, Customer, ScheduledSMS
from app.celery_tasks import schedule_sms_task


router = APIRouter(prefix="/conversations", tags=["Conversations"])

# -------------------------------
# GET full chat history for a specific customer
# -------------------------------
@router.get("/{customer_id}")
def get_conversation(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    engagements = db.query(Engagement)\
        .filter(Engagement.customer_id == customer_id)\
        .all()

    scheduled_sms = db.query(ScheduledSMS)\
        .filter(ScheduledSMS.customer_id == customer_id)\
        .all()

    conversation = []

    for msg in engagements:
        if msg.response:
            conversation.append({
                "sender": "customer",
                "text": msg.response,
                "timestamp": msg.sent_at,
                "source": "customer_response",
                "direction": "incoming"
            })
        if msg.ai_response and msg.status != "sent":
            conversation.append({
                "sender": "ai",
                "text": msg.ai_response,
                "timestamp": None,
                "source": "ai_draft",
                "direction": "outgoing"
            })
        if msg.ai_response and msg.status == "sent":
            conversation.append({
                "sender": "owner",
                "text": msg.ai_response,
                "timestamp": msg.sent_at,
                "source": "manual_reply",
                "direction": "outgoing"
            })

    for sms in scheduled_sms:
        conversation.append({
            "sender": "owner",
            "text": sms.message,
            "timestamp": sms.send_time,
            "source": "scheduled_sms",
            "direction": "outgoing"
        })

    sorted_conversation = sorted(
        conversation,
        key=lambda m: m["timestamp"] or datetime.min
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

@router.post("/{customer_id}/reply")
def send_manual_reply(customer_id: int, payload: ManualReplyInput, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now = datetime.utcnow()

    # 1. Save to Engagements (for conversation history)
    new_msg = Engagement(
        customer_id=customer.id,
        response=None,
        ai_response=payload.message,
        status="sent",
        sent_at=now,
    )
    db.add(new_msg)

    # 2. Save to ScheduledSMS (for actual SMS delivery)
    scheduled_sms = ScheduledSMS(
        customer_id=customer.id,
        business_id=customer.business_id,
        message=payload.message,
        status="scheduled",
        send_time=now,
    )
    db.add(scheduled_sms)

    # 3. Commit once (so scheduled_sms.id exists)
    db.commit()

    # 4. Trigger Celery task
    schedule_sms_task.delay(scheduled_sms.id)

    return {"message": "Reply sent and scheduled"}

# -------------------------------
# GET inbox summary: all customers with conversations
# -------------------------------
@router.get("/")
def get_conversation_inbox(db: Session = Depends(get_db)):
    # 1. Get all customers who have at least one engagement
    customers = db.query(Customer).all()
    inbox = []

    for customer in customers:
        latest = db.query(Engagement)\
            .filter(Engagement.customer_id == customer.id)\
            .order_by(Engagement.id.desc())\
            .first()

        if latest and latest.status == "pending_review":
            inbox.append({
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "last_message": latest.response or latest.ai_response,
                "status": latest.status,
                "timestamp": latest.sent_at.isoformat() if latest and latest.sent_at else None
            })

    # Sort by most recent
    inbox.sort(key=lambda x: x["timestamp"] or "", reverse=True)

    return {"conversations": inbox}