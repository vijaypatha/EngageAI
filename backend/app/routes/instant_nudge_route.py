# instant_nudge_route.py
# Routes for generating and sending Instant Nudges – AI-personalized SMS messages
# Supports drafting based on topic and multi-customer delivery (immediate or scheduled)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from app.services.instant_nudge_service import generate_instant_nudge
import logging

router = APIRouter()

# Payload model for generating a single nudge message
class InstantNudgeRequest(BaseModel):
    topic: str
    business_id: int
    customer_ids: List[int]

# Endpoint to generate an AI-personalized message based on a topic
@router.post("/instant-nudge/generate-message")
async def generate_instant_nudge_message(payload: InstantNudgeRequest):
    logging.info(f"✍️ Received Instant Nudge generation request for business_id={payload.business_id} | topic='{payload.topic}'")
    try:
        logging.debug(f"Payload details: {payload.json()}")
        return await generate_instant_nudge(payload.topic, payload.business_id)
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