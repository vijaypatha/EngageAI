# instant_nudge_route.py
# Routes for generating and sending Instant Nudges – AI-personalized SMS messages
# Supports drafting based on topic and multi-customer delivery (immediate or scheduled)

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from app.services.instant_nudge_service import generate_instant_nudge
import logging
from app.models import BusinessProfile, Message, Conversation
from sqlalchemy.orm import Session
from app.database import get_db
from datetime import datetime, timezone
from sqlalchemy import func

router = APIRouter()

# Payload model for generating a single nudge message
class InstantNudgeRequest(BaseModel):
    topic: str
    business_id: int
    customer_ids: List[int]

# Endpoint to generate an AI-personalized message based on a topic
@router.post("/instant-nudge/generate-message")
async def generate_instant_nudge_message(
    payload: InstantNudgeRequest,
    db: Session = Depends(get_db)
):
    logging.info(f"✍️ Received Instant Nudge generation request for business_id={payload.business_id} | topic='{payload.topic}'")
    try:
        logging.debug(f"Payload details: {payload.json()}")
        return await generate_instant_nudge(payload.topic, payload.business_id, db)
    except Exception as e:
        logging.error(f"❌ Instant Nudge generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate instant nudge message")

# Payload model for sending multiple nudges to customers (supports optional scheduling)
class InstantNudgeBatch(BaseModel):
    messages: List[dict]  # Each dict has customer_ids, message, send_datetime_utc (nullable)

from app.services.instant_nudge_service import handle_instant_nudge_batch

# Endpoint to send or schedule multiple AI-personalized messages
@router.post("/nudge/instant-multi")
async def send_instant_nudge_batch(payload: InstantNudgeBatch):
    logging.info(f"📨 Received Instant Nudge batch send request with {len(payload.messages)} message blocks")
    try:
        logging.debug(f"Payload details: {payload.json()}")
        return await handle_instant_nudge_batch(payload.messages)
    except Exception as e:
        logging.error(f"❌ Failed to send instant nudges: {e}")
        raise HTTPException(status_code=500, detail="Failed to send instant nudges")

# Endpoint to get the status of instant nudges by slug
@router.get("/nudge/instant-status/slug/{slug}")
def get_instant_nudge_status(slug: str, db: Session = Depends(get_db)):
    business = db.query(BusinessProfile).filter(BusinessProfile.slug == slug).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Get all conversations for this business
    conversations = db.query(Conversation).filter(
        Conversation.business_id == business.id
    ).all()
    
    # Get all instant nudge messages for these conversations
    messages = db.query(Message).filter(
        Message.business_id == business.id,
        Message.message_type == 'scheduled',
        func.jsonb_exists(Message.message_metadata, 'source'),
        Message.message_metadata.op('->>')('source') == 'instant_nudge'
    ).all()

    return [
        {
            "id": m.id,
            "message": m.content,
            "customer_id": m.customer_id,
            "status": m.status,
            "send_time": m.scheduled_time,
            "is_hidden": m.is_hidden,
            "conversation_id": m.conversation_id,
            "metadata": m.message_metadata
        }
        for m in messages
    ]

# Endpoint to get detailed instant nudge analytics
@router.get("/nudge/instant-analytics/business/{business_id}")
def get_instant_nudge_analytics(business_id: int, db: Session = Depends(get_db)):
    now_utc = datetime.now(timezone.utc)
    
    messages = db.query(Message).filter(
        Message.business_id == business_id,
        Message.message_type == 'scheduled',
        func.jsonb_exists(Message.message_metadata, 'source'),
        Message.message_metadata.op('->>')('source') == 'instant_nudge'
    ).all()

    # Calculate analytics
    total_sent = sum(1 for m in messages if m.status == 'sent')
    total_pending = sum(1 for m in messages if m.status == 'pending')
    total_failed = sum(1 for m in messages if m.status == 'failed')
    total_scheduled = sum(1 for m in messages if m.status == 'scheduled' and m.scheduled_time and m.scheduled_time > now_utc)

    return {
        "total_messages": len(messages),
        "sent": total_sent,
        "pending": total_pending,
        "failed": total_failed,
        "scheduled": total_scheduled,
        "success_rate": (total_sent / len(messages)) if messages else 0
    }
# Endpoint to get all instant nudge messages for a customer (immediate and scheduled)
@router.get("/nudge/instant-multi/customer/{customer_id}")
def get_instant_nudges_for_customer(customer_id: int, db: Session = Depends(get_db)):
    messages = db.query(Message).filter(
        Message.customer_id == customer_id,
        func.jsonb_exists(Message.message_metadata, 'source'),
        Message.message_metadata.op('->>')('source') == 'instant_nudge'
    ).order_by(Message.scheduled_time.desc()).all()

    return [
        {
            "id": m.id,
            "message": m.content,
            "customer_id": m.customer_id,
            "status": m.status,
            "send_time": m.scheduled_time,
            "is_hidden": m.is_hidden,
            "conversation_id": m.conversation_id,
            "metadata": m.message_metadata
        }
        for m in messages
    ]