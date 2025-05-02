print("✅ review.py loaded")

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import RoadmapMessage, Message, Customer, Engagement, ConsentLog, Conversation
from datetime import datetime, timezone
from sqlalchemy import and_, func, desc, cast, Integer, JSON
from sqlalchemy.dialects.postgresql import JSONB
from app.celery_tasks import schedule_sms_task
from app.services import MessageService
from app.services.stats_service import get_stats_for_business as get_stats_for_business, calculate_reply_stats
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

@router.get("/all-engagements")
def get_all_engagements(business_id: int, db: Session = Depends(get_db)):
    """Get all engagement data for a business"""
    # Get all customers for this business
    customers = db.query(Customer).filter(
        Customer.business_id == business_id
    ).all()

    result = []
    now_utc = datetime.now(timezone.utc)

    for customer in customers:
        # Get latest consent status
        latest_consent = (
            db.query(ConsentLog)
            .filter(ConsentLog.customer_id == customer.id)
            .order_by(desc(ConsentLog.replied_at))
            .first()
        )

        consent_status = latest_consent.status if latest_consent else "pending"
        consent_updated = latest_consent.replied_at if latest_consent else None
        opted_in = latest_consent.status == "opted_in" if latest_consent else False

        # Get roadmap messages
        roadmap = db.query(RoadmapMessage).filter(
            RoadmapMessage.customer_id == customer.id,
            RoadmapMessage.status != "deleted"
        ).all()

        # Get scheduled messages
        scheduled = db.query(Message).filter(
            Message.customer_id == customer.id,
            Message.message_type == 'scheduled'
        ).all()

        # Format messages
        messages = []
        for msg in roadmap:
            if msg.send_datetime_utc and msg.send_datetime_utc >= now_utc:
                messages.append(format_roadmap_message(msg))

        for msg in scheduled:
            if msg.scheduled_time and msg.scheduled_time >= now_utc:
                messages.append(format_message(msg))

        if messages:  # Only include customers with messages
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
    for reply in replies:
        customer = db.query(Customer).filter(Customer.id == reply.customer_id).first()
        if customer:
            result.append({
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "response": reply.response,
                "ai_response": reply.ai_response,
                "status": reply.status,
                "sent_at": reply.sent_at.isoformat() if reply.sent_at else None
            })

    return result

@router.post("/debug/send-sms-now/{message_id}")
def debug_send_sms_now(message_id: int):
    """Debug endpoint to trigger immediate send of a scheduled message"""
    print(f"🚨 Manually triggering SMS for Message id={message_id}")
    schedule_sms_task.apply_async(args=[message_id])
    return {"status": "triggered"}

@router.get("/full-customer-history")
def get_full_customer_history(
    business_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Get complete message history for all customers"""
    # Get latest consent status for each customer
    customers = db.query(Customer).filter(
        Customer.business_id == business_id
    ).all()

    result = []
    for customer in customers:
        # Get latest consent
        latest_consent = (
            db.query(ConsentLog)
            .filter(ConsentLog.customer_id == customer.id)
            .order_by(desc(ConsentLog.replied_at))
            .first()
        )

        # Validate consent status consistency
        consent_status = latest_consent.status if latest_consent else "pending"
        opted_in = latest_consent.status == "opted_in" if latest_consent else False

        # Get all messages
        messages = db.query(Message).filter(
            Message.customer_id == customer.id,
            Message.message_type == 'scheduled'
        ).order_by(Message.scheduled_time.desc()).all()

        # Get all engagements
        engagements = db.query(Engagement).filter(
            Engagement.customer_id == customer.id
        ).order_by(Engagement.sent_at.desc()).all()

        # Format messages
        message_history = []

        # 1. Add customer replies (inbound, left)
        for eng in engagements:
            if eng.response:
                message_history.append({
                    "type": "customer",
                    "content": eng.response,
                    "sent_time": eng.sent_at.isoformat() if eng.sent_at else None,
                    "source": "customer_reply",
                    "status": "sent",
                    "customer_id": eng.customer_id,
                    "id": eng.id,
                    "is_hidden": False
                })

        # 2. Add business-sent messages (outbound, right)
        for msg in messages:
            if msg.status == "sent":
                message_history.append({
                    "type": "sent",
                    "content": msg.content,
                    "status": msg.status,
                    "scheduled_time": msg.scheduled_time.isoformat() if msg.scheduled_time else None,
                    "sent_time": msg.sent_at.isoformat() if msg.sent_at else None,
                    "source": msg.message_metadata.get('source', 'scheduled') if msg.message_metadata else 'scheduled',
                    "customer_id": msg.customer_id,
                    "id": msg.id,
                    "is_hidden": msg.is_hidden if hasattr(msg, 'is_hidden') else False
                })

        # 3. Add AI drafts (outbound, right, not sent yet)
        for eng in engagements:
            if eng.ai_response and eng.status != "sent":
                message_history.append({
                    "type": "ai_draft",
                    "content": eng.ai_response,
                    "status": eng.status,
                    "sent_time": eng.sent_at.isoformat() if eng.sent_at else None,
                    "source": "ai_response",
                    "customer_id": eng.customer_id,
                    "id": eng.id,
                    "is_hidden": False
                })

        # Sort by time
        message_history.sort(
            key=lambda x: x.get("sent_time") or x.get("scheduled_time") or "",
            reverse=True
        )

        result.append({
            "customer_id": customer.id,
            "customer_name": customer.customer_name,
            "phone": customer.phone,
            "opted_in": opted_in,
            "consent_status": consent_status,
            "consent_updated": latest_consent.replied_at.isoformat() if latest_consent else None,
            "message_count": len(message_history),
            "messages": message_history
        })

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