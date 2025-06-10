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
        processed_sent_message_ids_from_messages_table = set()

        # 1. Process the 'messages' table (typically outbound scheduled/direct messages)
        customer_messages_from_message_table = db.query(Message).filter(
            Message.customer_id == customer.id
        ).order_by(Message.created_at.asc()).all()

        for msg_record in customer_messages_from_message_table:
            if msg_record.is_hidden:
                continue
            if msg_record.status == "sent":
                logger.debug(f"Adding from messages table: msg_id={msg_record.id}, content='{msg_record.content[:30]}...'")
                message_history.append({
                    "id": f"msg-{msg_record.id}",
                    "type": "sent",
                    "content": msg_record.content,
                    "status": msg_record.status,
                    "scheduled_time": msg_record.scheduled_time.isoformat() if msg_record.scheduled_time else None,
                    "sent_time": msg_record.sent_at.isoformat() if msg_record.sent_at else None,
                    "source": msg_record.message_metadata.get('source', 'scheduled') if msg_record.message_metadata else 'scheduled',
                    "customer_id": msg_record.customer_id,
                    "is_hidden": msg_record.is_hidden,
                })
                processed_sent_message_ids_from_messages_table.add(msg_record.id)
            # Add other statuses from Message table if needed (e.g., "scheduled")

        # 2. Process 'engagements' table (customer replies, AI drafts, and AI sent replies not covered by messages table)
        customer_engagements = db.query(Engagement).filter(
            Engagement.customer_id == customer.id
        ).order_by(Engagement.created_at.asc()).all()

        for eng_record in customer_engagements:
            # Add customer's inbound message (their reply)
            if eng_record.response:
                logger.debug(f"Adding customer response from engagement: eng_id={eng_record.id}, response='{eng_record.response[:30]}...'")
                message_history.append({
                    "id": f"eng-cust-{eng_record.id}",
                    "type": "customer",
                    "content": eng_record.response,
                    "status": "received", # For clarity on frontend
                    "sent_time": eng_record.created_at.isoformat() if eng_record.created_at else None, # Customer message time = engagement creation time
                    "source": "customer_reply",
                    "customer_id": eng_record.customer_id,
                    "is_hidden": False, 
                })

            # Add AI response from the engagement (draft or sent)
            if eng_record.ai_response:
                logger.debug(f"Considering AI response from engagement: eng_id={eng_record.id}, status={eng_record.status}, message_id={eng_record.message_id}, ai_response='{eng_record.ai_response[:30]}...'")
                # Skip if this AI response was 'sent' AND it's linked to a Message record
                # that we've already processed from the `messages` table.
                # This prevents duplicating sent messages that exist in both tables.
                if eng_record.status == "sent" and \
                   eng_record.message_id and \
                   eng_record.message_id in processed_sent_message_ids_from_messages_table:
                    logger.debug(f"SKIPPING sent AI response from eng_id={eng_record.id} as message_id={eng_record.message_id} already processed.")
                    continue
                
                logger.debug(f"ADDING AI response from eng_id={eng_record.id}")
                message_type = "ai_draft" if eng_record.status != "sent" else "sent"
                message_history.append({
                    "id": f"eng-ai-{eng_record.id}",
                    "type": message_type,
                    "content": eng_record.ai_response,
                    "status": eng_record.status,
                    # sent_time is only for 'sent' type messages from engagements
                    "sent_time": eng_record.sent_at.isoformat() if eng_record.sent_at and message_type == "sent" else None,
                    "source": "ai_response_engagement",
                    "customer_id": eng_record.customer_id,
                    "is_hidden": False, 
                })
        
        message_history.sort(
            key=lambda x: datetime.fromisoformat(x.get("sent_time").replace("Z", "+00:00")) if x.get("sent_time") else datetime.min.replace(tzinfo=timezone.utc)
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