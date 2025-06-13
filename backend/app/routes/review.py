print("✅ review.py loaded")

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import RoadmapMessage, Message, Customer, Engagement, ConsentLog, Conversation
from datetime import datetime, timezone
from sqlalchemy import and_, func, desc, cast, Integer, JSON
from sqlalchemy.dialects.postgresql import JSONB
from app.celery_tasks import process_scheduled_message_task
from app.services import MessageService
from app.services import inbox_service # Uncommented and assuming it exists
from app.services.stats_service import get_stats_for_business as get_stats_for_business, calculate_reply_stats
from app.schemas import PaginatedInboxSummaries # Import the new schema
import logging
import uuid
import pytz

logger = logging.getLogger(__name__)

def format_roadmap_message(msg: RoadmapMessage) -> dict:
    """Format a roadmap message for API response"""
    return {
        "id": msg.id,
        "smsContent": msg.smsContent,
        "smsTiming": msg.smsTiming,
        "status": msg.status,
        "relevance": getattr(msg, "relevance", None),
        "successIndicator": getattr(msg, "successIndicator", None),
        "send_datetime_utc": msg.send_datetime_utc.isoformat() if msg.send_datetime_utc else None,
        "source": "roadmap"
    }

def format_message(msg: Message) -> dict:
    """Format a message for API response"""
    return {
        "id": msg.id,
        "smsContent": msg.content,
        "smsTiming": msg.scheduled_time.strftime("Scheduled: %b %d, %I:%M %p") if msg.scheduled_time else None,
        "status": msg.status,
        "send_datetime_utc": msg.scheduled_time.isoformat() if msg.scheduled_time else None,
        "source": msg.message_metadata.get('source', 'scheduled') if msg.message_metadata else 'scheduled'
    }

router = APIRouter()

@router.get("/engagement-plan/{customer_id}")
def get_engagement_plan(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now_utc = datetime.now(timezone.utc)

    # Get latest consent status
    latest_consent = (
        db.query(ConsentLog)
        .filter(ConsentLog.customer_id == customer_id)
        .order_by(desc(ConsentLog.replied_at))
        .first()
    )

    consent_status = latest_consent.status if latest_consent else "pending"
    opted_in = latest_consent.status == "opted_in" if latest_consent else False

    # Get roadmap messages that haven't been scheduled yet
    roadmap_messages = db.query(RoadmapMessage).filter(
        and_(
            RoadmapMessage.customer_id == customer_id,
            RoadmapMessage.send_datetime_utc != None,
            RoadmapMessage.send_datetime_utc >= now_utc,
            RoadmapMessage.status != "deleted",
            RoadmapMessage.status != "scheduled"  # Don't include already scheduled messages
        )
    ).all()

    # Get scheduled messages
    scheduled_messages = db.query(Message).filter(
        and_(
            Message.customer_id == customer_id,
            Message.message_type == 'scheduled',
            Message.scheduled_time != None,
            Message.scheduled_time >= now_utc
        )
    ).all()

    roadmap_data = [format_roadmap_message(msg) for msg in roadmap_messages]
    scheduled_data = [format_message(msg) for msg in scheduled_messages]

    return {
        "engagements": roadmap_data + scheduled_data,
        "latest_consent_status": consent_status,
        "opted_in": opted_in
    }


@router.get("/stats/{business_id}")
def get_stats(business_id: int, db: Session = Depends(get_db)):
    """API endpoint for getting message counts by status"""
    return get_stats_for_business(business_id, db)

@router.get("/reply-stats/{business_id}")
def get_reply_stats(business_id: int, db: Session = Depends(get_db)):
    """API endpoint for getting reply stats"""
    return calculate_reply_stats(business_id, db)

@router.get("/customers/without-engagement-count/{business_id}")
def get_contact_stats(business_id: int, db: Session = Depends(get_db)):
    """Get count of customers without any engagement"""
    total_customers = db.query(Customer).filter(
        Customer.business_id == business_id
    ).count()

    customers_with_messages = db.query(Customer.id).distinct().join(Message).filter(
        Customer.business_id == business_id
    ).count()

    return {
        "total_customers": total_customers,
        "customers_without_engagement": total_customers - customers_with_messages
    }

# Replace the existing get_all_engagements function with this one.

@router.get("/all-engagements")
def get_all_engagements(business_id: int, db: Session = Depends(get_db)):
    """
    Get all engagement data for a business.
    This version ensures that once a roadmap message is scheduled, only the
    authoritative 'Message' record is returned, preventing duplicates.
    """
    customers = db.query(Customer).filter(
        Customer.business_id == business_id
    ).all()

    result = []
    now_utc = datetime.now(timezone.utc)

    for customer in customers:
        latest_consent = (
            db.query(ConsentLog)
            .filter(ConsentLog.customer_id == customer.id)
            .order_by(desc(ConsentLog.replied_at))
            .first()
        )
        consent_status = latest_consent.status if latest_consent else "pending"
        consent_updated = latest_consent.replied_at if latest_consent else None
        opted_in = consent_status == "opted_in"

        # --- THIS IS THE FIX ---
        # We only fetch roadmap messages that are still pending.
        # Once a message is 'scheduled' or 'superseded', it is handled by the 'Message' table query.
        # This prevents sending the original "ghost" record to the frontend.
        valid_roadmap_statuses = ["draft", "pending_review"]  # Add any other unscheduled statuses you use
        roadmap = db.query(RoadmapMessage).filter(
            RoadmapMessage.customer_id == customer.id,
            RoadmapMessage.status.in_(valid_roadmap_statuses)
        ).all()

        # Get all scheduled messages (this query is correct)
        scheduled = db.query(Message).filter(
            Message.customer_id == customer.id,
            Message.message_type == 'scheduled'
        ).all()

        messages = []
        # Add future-dated, pending roadmap messages
        for msg in roadmap:
            if msg.send_datetime_utc and msg.send_datetime_utc >= now_utc:
                # Add a customer_timezone field to be consistent with the other message type
                formatted_msg = format_roadmap_message(msg)
                formatted_msg["customer_timezone"] = customer.timezone
                messages.append(formatted_msg)

        # Add future-dated, scheduled messages
        for msg in scheduled:
            if msg.scheduled_time and msg.scheduled_time >= now_utc:
                formatted_msg = format_message(msg)
                # Add a customer_timezone field to be consistent with the other message type
                formatted_msg["customer_timezone"] = customer.timezone
                messages.append(formatted_msg)

        if messages:
            result.append({
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "opted_in": opted_in,
                "latest_consent_status": consent_status,
                "latest_consent_updated": consent_updated.isoformat() if consent_updated else None,
                "messages": sorted(messages, key=lambda x: x["send_datetime_utc"] or "")
            })

    return result

@router.put("/update-time-debug/{id}")
def debug_update_message_time(
    id: int,
    source: str = Query(...),
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    print("✅ REACHED DEBUG ENDPOINT")
    print(f"ID={id}, Source={source}, Payload={payload}")
    return {"received": True, "id": id, "payload": payload, "source": source}

@router.get("/customer-replies")
def get_customer_replies(
    business_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Get all customer replies for a business"""
    replies = db.query(Engagement).join(Customer).filter(
        Customer.business_id == business_id,
        Engagement.response != None
    ).order_by(Engagement.sent_at.desc()).all()

    result = []
    for reply_engagement in replies: # Renamed loop variable for clarity
        customer = db.query(Customer).filter(Customer.id == reply_engagement.customer_id).first()
        if customer:
            result.append({
                "id": reply_engagement.id,  # <--- THIS IS THE PRIMARY FIX (Engagement ID)
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "phone": customer.phone, # Added from Customer model
                "response": reply_engagement.response, # Customer's message
                "ai_response": reply_engagement.ai_response, # AI's draft for this engagement
                "status": reply_engagement.status,
                # Use engagement's created_at for the customer's message timestamp
                "timestamp": reply_engagement.created_at.isoformat() if reply_engagement.created_at else None,
                "lifecycle_stage": customer.lifecycle_stage,
                "pain_points": customer.pain_points,
                "interaction_history": customer.interaction_history,
                # Note: 'last_message' from CustomerReply interface is ambiguous here;
                # 'response' (customer's message) or 'ai_response' (AI's message) are more specific.
                # 'sent_at' in the original code referred to the engagement's sent_at,
                # which is for when the AI's reply was sent. We'll keep it if useful,
                # but 'timestamp' above is likely for the customer's message.
                "engagement_sent_at": reply_engagement.sent_at.isoformat() if reply_engagement.sent_at else None
            })
    return result

@router.post("/debug/send-sms-now/{message_id}")
def debug_send_sms_now(message_id: int):
    """Debug endpoint to trigger immediate send of a scheduled message"""
    print(f"🚨 Manually triggering SMS for Message id={message_id}")
    process_scheduled_message_task.apply_async(args=[message_id])
    return {"status": "triggered"}

@router.get("/full-customer-history")
def get_full_customer_history(
    business_id: int = Query(...),
    db: Session = Depends(get_db)
):
    logger.info(f"Fetching full customer history for business_id: {business_id}")
    customers = db.query(Customer).filter(Customer.business_id == business_id).all()
    result = []

    for customer in customers:
        logger.debug(f"Processing customer_id: {customer.id}")
        latest_consent = (
            db.query(ConsentLog)
            .filter(ConsentLog.customer_id == customer.id)
            .order_by(desc(ConsentLog.replied_at))
            .first()
        )
        consent_status = latest_consent.status if latest_consent else "pending"
        opted_in = consent_status == "opted_in"

        message_history = []

        # 1. Get all messages from the Message table (outbound, scheduled, etc.)
        all_db_messages = db.query(Message).filter(
            Message.customer_id == customer.id
        ).all()

        for msg in all_db_messages:
            if msg.is_hidden:
                continue

            # Pass the backend message_type ('outbound', 'scheduled', etc.) directly
            message_history.append({
                "id": f"msg-{msg.id}",
                "type": msg.message_type,
                "content": msg.content,
                "status": msg.status,
                "scheduled_time": msg.scheduled_time.isoformat() if msg.scheduled_time else None,
                "sent_time": msg.sent_at.isoformat() if msg.sent_at else None,
                "source": msg.message_metadata.get('source') if msg.message_metadata else None,
                "customer_id": msg.customer_id,
                "is_hidden": msg.is_hidden,
                "timestamp_for_sorting": msg.sent_at or msg.scheduled_time or msg.created_at
            })

        # 2. Get all inbound replies and their associated AI drafts from the Engagement table
        all_engagements = db.query(Engagement).filter(
            Engagement.customer_id == customer.id
        ).all()
        
        for eng in all_engagements:
            # Create a record for the customer's inbound message
            if eng.response:
                message_history.append({
                    "id": f"eng-cust-{eng.id}",
                    "type": "inbound",  # Use 'inbound' for customer replies
                    "content": eng.response,
                    "response": eng.response, # Also map to response for frontend compatibility
                    "status": "received",
                    "sent_time": eng.created_at.isoformat(), # The time we received the message
                    "customer_id": eng.customer_id,
                    "timestamp_for_sorting": eng.created_at
                })
            
            # Create a separate record for the AI draft associated with the reply
            if eng.ai_response and eng.status != "auto_replied_faq":
                # auto_replied_faq is already captured in the Message table, so we skip it here to avoid duplicates
                message_history.append({
                    "id": f"eng-ai-{eng.id}",
                    "type": "ai_draft",
                    "ai_response": eng.ai_response,
                    "status": eng.status,
                    "customer_id": eng.customer_id,
                    "timestamp_for_sorting": eng.created_at
                })

        # 3. Sort the combined history by a consistent timestamp
        message_history.sort(
            key=lambda x: x.get("timestamp_for_sorting") or datetime.min.replace(tzinfo=timezone.utc),
            reverse=False
        )

        result.append({
            "customer_id": customer.id,
            "customer_name": customer.customer_name,
            "phone": customer.phone,
            "opted_in": opted_in,
            "consent_status": consent_status,
            "consent_updated": latest_consent.replied_at.isoformat() if latest_consent and latest_consent.replied_at else None,
            "message_count": len(message_history),
            "messages": message_history
        })
        
    logger.info(f"Finished processing history for business_id: {business_id}. Total customers processed: {len(customers)}")
    return result

@router.get("/review/customer-id/from-message/{message_id}")
def get_customer_id_from_message(message_id: int, db: Session = Depends(get_db)):
    """Get customer ID from a message ID"""
    message = db.query(Message).filter(
        Message.id == message_id,
        Message.message_type == 'scheduled'
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"customer_id": message.customer_id}


@router.put("/hide-sent/{message_id}")
def hide_sent_message(message_id: int, hide: bool = Query(True), db: Session = Depends(get_db)):
    """Hide or unhide a sent message"""
    message = db.query(Message).filter(
        Message.id == message_id,
        Message.message_type == 'scheduled'
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    message.is_hidden = hide
    db.commit()
    print(f"🙈 Message ID={message_id} marked as {'hidden' if hide else 'visible'}")
    return {"status": "success", "is_hidden": hide}

@router.get("/v2/engagement-plan/{customer_id}")
def get_engagement_plan_v2(customer_id: int, db: Session = Depends(get_db)):
    """Get engagement plan with additional metadata"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now_utc = datetime.now(timezone.utc)

    # Get latest consent status
    latest_consent = (
        db.query(ConsentLog)
        .filter(ConsentLog.customer_id == customer_id)
        .order_by(desc(ConsentLog.replied_at))
        .first()
    )

    consent_status = latest_consent.status if latest_consent else "pending"

    # Get roadmap messages that haven't been scheduled yet
    roadmap_messages = db.query(RoadmapMessage).filter(
        and_(
            RoadmapMessage.customer_id == customer_id,
            RoadmapMessage.send_datetime_utc != None,
            RoadmapMessage.send_datetime_utc >= now_utc,
            RoadmapMessage.status != "deleted",
            RoadmapMessage.status != "scheduled"
        )
    ).all()

    # Get scheduled messages
    scheduled_messages = db.query(Message).filter(
        and_(
            Message.customer_id == customer_id,
            Message.message_type == 'scheduled',
            Message.scheduled_time != None,
            Message.scheduled_time >= now_utc
        )
    ).all()

    roadmap_data = []
    for msg in roadmap_messages:
        data = format_roadmap_message(msg)
        data["metadata"] = {
            "relevance": msg.relevance,
            "success_indicator": msg.success_indicator,
            "no_response_plan": msg.no_response_plan
        }
        roadmap_data.append(data)

    scheduled_data = []
    for msg in scheduled_messages:
        data = format_message(msg)
        data["metadata"] = msg.message_metadata or {}
        scheduled_data.append(data)

    return {
        "customer": {
            "id": customer.id,
            "name": customer.customer_name,
            "phone": customer.phone,
            "consent_status": consent_status
        },
        "engagements": roadmap_data + scheduled_data
    }

@router.get("/received-messages/{business_id}")
def get_received_messages_count(business_id: int, db: Session = Depends(get_db)):
    received_count = db.query(Engagement).filter(
        Engagement.business_id == business_id,
        Engagement.response != None
    ).count()
    return {"received_count": received_count}

@router.get("/inbox/summaries", response_model=PaginatedInboxSummaries)
def get_inbox_summaries(
    business_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get paginated inbox summaries for a business.
    Includes customer info, last message snippet, timestamp, and unread count.
    """
    summaries, total_count = inbox_service.get_paginated_inbox_summaries(
        db=db, business_id=business_id, page=page, size=size
    )

    return {
        "items": summaries,
        "total": total_count,
        "page": page,
        "size": size,
        "pages": (total_count + size - 1) // size
    }