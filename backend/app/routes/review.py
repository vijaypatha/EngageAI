# backend/app/routes/review.py

print("✅ review.py loaded")

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from app.database import get_db
# Added MessageTypeEnum to the import
from app.models import RoadmapMessage, Message, Customer, Engagement, ConsentLog, Conversation, MessageTypeEnum, MessageStatusEnum
from datetime import datetime, timezone
from sqlalchemy import and_, func, desc, cast, Integer, JSON # Unused: cast, Integer, JSON, JSONB in this file
from sqlalchemy.dialects.postgresql import JSONB # Unused in this file
from app.celery_tasks import process_scheduled_message_task
# from app.services import MessageService # Unused in this file
from app.services.stats_service import get_stats_for_business, calculate_reply_stats # get_stats_for_business was imported twice, fixed
import logging
# import uuid # Unused in this file
# import pytz # Unused in this file

logger = logging.getLogger(__name__)

def format_roadmap_message(msg: RoadmapMessage) -> dict:
    """Format a roadmap message for API response"""
    return {
        "id": msg.id,
        "smsContent": msg.smsContent,
        "smsTiming": msg.smsTiming, # smsTiming is a string from the model, not a datetime object itself
        "status": msg.status,
        "relevance": getattr(msg, "relevance", None),
        # "successIndicator": getattr(msg, "successIndicator", None), # Mismatch: model has success_indicator
        "success_indicator": getattr(msg, "success_indicator", None),
        "send_datetime_utc": msg.send_datetime_utc.isoformat() if msg.send_datetime_utc else None,
        "source": "roadmap"
    }

def format_message(msg: Message) -> dict:
    """Format a message for API response"""
    return {
        "id": msg.id,
        "smsContent": msg.content,
        # Changed msg.scheduled_time to msg.scheduled_send_at
        "smsTiming": msg.scheduled_send_at.strftime("Scheduled: %b %d, %I:%M %p") if msg.scheduled_send_at else None,
        "status": msg.status,
        # Changed msg.scheduled_time to msg.scheduled_send_at
        "send_datetime_utc": msg.scheduled_send_at.isoformat() if msg.scheduled_send_at else None,
        "source": msg.message_metadata.get('source', 'scheduled') if msg.message_metadata else 'scheduled'
    }

router = APIRouter()

@router.get("/engagement-plan/{customer_id}")
def get_engagement_plan(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now_utc = datetime.now(timezone.utc)

    latest_consent = (
        db.query(ConsentLog)
        .filter(ConsentLog.customer_id == customer_id)
        .order_by(desc(ConsentLog.replied_at)) # Assuming replied_at indicates latest interaction for consent
        .first()
    )

    # OptInStatus values are lowercase e.g. "opted_in"
    consent_status = latest_consent.status.value if latest_consent and latest_consent.status else "pending"
    opted_in = consent_status == "opted_in"

    roadmap_messages = db.query(RoadmapMessage).filter(
        and_(
            RoadmapMessage.customer_id == customer_id,
            RoadmapMessage.send_datetime_utc != None,
            RoadmapMessage.send_datetime_utc >= now_utc,
            RoadmapMessage.status != MessageStatusEnum.DELETED, # Use enum member for comparison
            RoadmapMessage.status != MessageStatusEnum.SCHEDULED # Use enum member
        )
    ).all()

    scheduled_messages = db.query(Message).filter(
        and_(
            Message.customer_id == customer_id,
            Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE, # Corrected comparison
            Message.scheduled_send_at != None,      # Corrected attribute
            Message.scheduled_send_at >= now_utc    # Corrected attribute
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
    return get_stats_for_business(business_id, db)

@router.get("/reply-stats/{business_id}")
def get_reply_stats(business_id: int, db: Session = Depends(get_db)):
    return calculate_reply_stats(business_id, db)

@router.get("/customers/without-engagement-count/{business_id}")
def get_contact_stats(business_id: int, db: Session = Depends(get_db)):
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

@router.get("/all-engagements") # This endpoint seems to be for a general review, not just "engagements" table
def get_all_engagements_review(business_id: int, db: Session = Depends(get_db)): # Renamed for clarity
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

        consent_status = latest_consent.status.value if latest_consent and latest_consent.status else "pending"
        consent_updated = latest_consent.replied_at if latest_consent else None
        opted_in = consent_status == "opted_in"

        messages_to_display = [] # Renamed for clarity
        
        # Roadmap messages that are upcoming
        # Roadmap messages that are upcoming AND NOT YET SCHEDULED
        roadmap_items = db.query(RoadmapMessage).filter(
            RoadmapMessage.customer_id == customer.id,
            RoadmapMessage.status != MessageStatusEnum.DELETED,
            RoadmapMessage.status != MessageStatusEnum.SCHEDULED,  # <<< Key change: Exclude already scheduled
            RoadmapMessage.send_datetime_utc != None, # Ensure it has a send time
            RoadmapMessage.send_datetime_utc >= now_utc
        ).all()
        for msg in roadmap_items:
            messages_to_display.append(format_roadmap_message(msg))

        # Scheduled messages (from Message table) that are upcoming
        # Scheduled messages (from Message table) that are upcoming
        scheduled_message_items = db.query(Message).filter(
            Message.customer_id == customer.id,
            Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE,
            Message.scheduled_send_at != None,
            Message.scheduled_send_at >= now_utc
        ).all()
        for msg in scheduled_message_items:
             formatted_msg_data = format_message(msg)
             formatted_msg_data["source"] = "scheduled" # Ensure source is 'scheduled' for these items
             messages_to_display.append(formatted_msg_data)


        if messages_to_display: 
            result.append({
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "opted_in": opted_in,
                "latest_consent_status": consent_status,
                "latest_consent_updated": consent_updated.isoformat() if consent_updated else None,
                "messages": sorted(messages_to_display, key=lambda x: datetime.fromisoformat(x["send_datetime_utc"]) if x.get("send_datetime_utc") else datetime.min.replace(tzinfo=timezone.utc))
            })
    return result

@router.put("/update-time-debug/{id}")
def debug_update_message_time(
    id: int,
    source: str = Query(...),
    payload: dict = Body(...),
    db: Session = Depends(get_db) # db was unused
):
    print("✅ REACHED DEBUG ENDPOINT")
    print(f"ID={id}, Source={source}, Payload={payload}")
    # Example: if source == "roadmap":
    # item = db.query(RoadmapMessage).filter(RoadmapMessage.id == id).first()
    # if item and 'new_time' in payload: item.send_datetime_utc = payload['new_time']; db.commit()
    return {"received": True, "id": id, "payload": payload, "source": source}

@router.get("/customer-replies")
def get_customer_replies(
    business_id: int = Query(...),
    db: Session = Depends(get_db)
):
    replies = db.query(Engagement).join(Customer).filter(
        Customer.business_id == business_id,
        Engagement.response != None # Assuming Engagement.response holds the customer's reply text
    ).order_by(Engagement.created_at.desc()).all() # Order by when engagement (and thus reply) was created

    result = []
    for reply_engagement in replies: 
        customer = db.query(Customer).filter(Customer.id == reply_engagement.customer_id).first() # This could be optimized
        if customer:
            result.append({
                "id": reply_engagement.id, 
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "phone": customer.phone, 
                "response": reply_engagement.response, 
                "ai_response": reply_engagement.ai_response, 
                "status": reply_engagement.status.value if reply_engagement.status else None, # Use .value for enums if sending as string
                "timestamp": reply_engagement.created_at.isoformat() if reply_engagement.created_at else None,
                "lifecycle_stage": customer.lifecycle_stage,
                "pain_points": customer.pain_points,
                "interaction_history": customer.interaction_history,
                "engagement_sent_at": reply_engagement.sent_at.isoformat() if reply_engagement.sent_at else None
            })
    return result

@router.post("/debug/send-sms-now/{message_id}")
def debug_send_sms_now(message_id: int):
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
        # Use .value for enums when assigning to a string if that's the intent
        consent_status = latest_consent.status.value if latest_consent and latest_consent.status else "pending"
        opted_in = consent_status == "opted_in"

        message_history = []
        processed_sent_message_ids_from_messages_table = set()

        customer_messages_from_message_table = db.query(Message).filter(
            Message.customer_id == customer.id
        ).order_by(Message.created_at.asc()).all()

        for msg_record in customer_messages_from_message_table:
            if msg_record.is_hidden:
                continue
            # Example: Only add 'sent' messages from Message table to avoid double-counting 'scheduled' ones handled elsewhere
            # Adjust logic based on how you differentiate message sources
            if msg_record.status == MessageStatusEnum.SENT: # Use enum member for comparison
                logger.debug(f"Adding from messages table: msg_id={msg_record.id}, content='{msg_record.content[:30]}...'")
                message_history.append({
                    "id": f"msg-{msg_record.id}",
                    "type": "sent", # Or derive from msg_record.message_type.value
                    "content": msg_record.content,
                    "status": msg_record.status.value, # Use .value for enums if sending as string
                    # Corrected attribute name below:
                    "scheduled_time": msg_record.scheduled_send_at.isoformat() if msg_record.scheduled_send_at else None,
                    "sent_time": msg_record.sent_at.isoformat() if msg_record.sent_at else None,
                    "source": msg_record.message_metadata.get('source', 'message_table') if msg_record.message_metadata else 'message_table',
                    "customer_id": msg_record.customer_id,
                    "is_hidden": msg_record.is_hidden,
                })
                processed_sent_message_ids_from_messages_table.add(msg_record.id)
            
        customer_engagements = db.query(Engagement).filter(
            Engagement.customer_id == customer.id
        ).order_by(Engagement.created_at.asc()).all()

        for eng_record in customer_engagements:
            if eng_record.response:
                logger.debug(f"Adding customer response from engagement: eng_id={eng_record.id}, response='{eng_record.response[:30]}...'")
                message_history.append({
                    "id": f"eng-cust-{eng_record.id}",
                    "type": "customer", # This seems to represent inbound/received
                    "content": eng_record.response,
                    "status": "received", 
                    "sent_time": eng_record.created_at.isoformat() if eng_record.created_at else None, 
                    "source": "customer_reply",
                    "customer_id": eng_record.customer_id,
                    "is_hidden": False, 
                })

            if eng_record.ai_response:
                logger.debug(f"Considering AI response from engagement: eng_id={eng_record.id}, status={eng_record.status}, message_id={eng_record.message_id}, ai_response='{eng_record.ai_response[:30]}...'")
                if eng_record.status == MessageStatusEnum.SENT and \
                   eng_record.message_id and \
                   eng_record.message_id in processed_sent_message_ids_from_messages_table:
                    logger.debug(f"SKIPPING sent AI response from eng_id={eng_record.id} as message_id={eng_record.message_id} already processed.")
                    continue
                
                logger.debug(f"ADDING AI response from eng_id={eng_record.id}")
                message_type = "ai_draft" if eng_record.status != MessageStatusEnum.SENT else MessageTypeEnum.OUTBOUND_AI_REPLY.value # Example type
                message_history.append({
                    "id": f"eng-ai-{eng_record.id}",
                    "type": message_type,
                    "content": eng_record.ai_response,
                    "status": eng_record.status.value, # Use .value
                    "sent_time": eng_record.sent_at.isoformat() if eng_record.sent_at and eng_record.status == MessageStatusEnum.SENT else None,
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
            "consent_status": consent_status, # Already a string from .value or "pending"
            "consent_updated": latest_consent.replied_at.isoformat() if latest_consent and latest_consent.replied_at else None,
            "message_count": len(message_history),
            "messages": message_history
        })
    logger.info(f"Finished processing history for business_id: {business_id}. Total customers processed: {len(customers)}")
    return result

@router.get("/review/customer-id/from-message/{message_id}") # Path parameter name fixed
def get_customer_id_from_message_review(message_id: int, db: Session = Depends(get_db)): # Function name fixed for clarity
    message = db.query(Message).filter(
        Message.id == message_id,
        Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE # Corrected comparison
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"customer_id": message.customer_id}


@router.put("/hide-sent/{message_id}")
def hide_sent_message(message_id: int, hide: bool = Query(True), db: Session = Depends(get_db)):
    message = db.query(Message).filter(
        Message.id == message_id,
        # Assuming you only want to hide messages that were of type "scheduled_message"
        # If it can be any message type that was sent, this filter might be too restrictive or needs adjustment
        Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE # Corrected comparison
    ).first()
    if not message:
        # Consider if you want to allow hiding non-scheduled messages or if this is the intended logic
        raise HTTPException(status_code=404, detail="Scheduled message not found or not applicable for hiding")

    message.is_hidden = hide
    db.commit()
    print(f"🙈 Message ID={message_id} marked as {'hidden' if hide else 'visible'}")
    return {"status": "success", "is_hidden": hide}

@router.get("/v2/engagement-plan/{customer_id}")
def get_engagement_plan_v2(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now_utc = datetime.now(timezone.utc)

    latest_consent = (
        db.query(ConsentLog)
        .filter(ConsentLog.customer_id == customer_id)
        .order_by(desc(ConsentLog.replied_at))
        .first()
    )

    consent_status = latest_consent.status.value if latest_consent and latest_consent.status else "pending"

    roadmap_messages = db.query(RoadmapMessage).filter(
        and_(
            RoadmapMessage.customer_id == customer_id,
            RoadmapMessage.send_datetime_utc != None,
            RoadmapMessage.send_datetime_utc >= now_utc,
            RoadmapMessage.status != MessageStatusEnum.DELETED, # Use enum member
            RoadmapMessage.status != MessageStatusEnum.SCHEDULED # Use enum member
        )
    ).all()

    scheduled_messages = db.query(Message).filter(
        and_(
            Message.customer_id == customer_id,
            Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE, # Corrected comparison
            Message.scheduled_send_at != None,      # Corrected attribute
            Message.scheduled_send_at >= now_utc    # Corrected attribute
        )
    ).all()

    roadmap_data = []
    for msg in roadmap_messages:
        data = format_roadmap_message(msg)
        # Ensure 'relevance', 'success_indicator', 'no_response_plan' are actual attributes of RoadmapMessage model
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
            "consent_status": consent_status # Already a string from .value or "pending"
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