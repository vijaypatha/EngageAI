# stats_service.py

from sqlalchemy.orm import Session
from app.models import Customer, RoadmapMessage, Message, Engagement, ConsentLog
from sqlalchemy import func, desc
from loguru import logger

def get_stats_for_business(business_id: int, db: Session):
    logger.info(f"📊 Fetching dashboard stats for business_id={business_id}")

    # Community size = count of customers
    communitySize = db.query(Customer).filter(Customer.business_id == business_id).count()
    logger.info(f"👥 Community size: {communitySize}")

    # Replace the simple opt-in status counting with a more accurate approach
    optedIn = optedOut = optInPending = 0
    
    # Get all customers for this business
    customers = db.query(Customer).filter(Customer.business_id == business_id).all()
    
    for customer in customers:
        # Get latest consent status from ConsentLog
        latest_consent = (
            db.query(ConsentLog)
            .filter(
                ConsentLog.phone_number == customer.phone,
                ConsentLog.business_id == business_id
                )
            .order_by(desc(ConsentLog.replied_at))
            .first()
        )
        
        if latest_consent:
            if latest_consent.status == "opted_in":
                optedIn += 1
            elif latest_consent.status == "opted_out":
                optedOut += 1
            elif latest_consent.status in ["pending", "waiting"]:
                optInPending += 1
        else:
            # No consent log means pending
            optInPending += 1
    
    logger.info(f"✅ Opted In: {optedIn}, ⏳ Waiting: {optInPending}, ❌ Opted Out: {optedOut}")

    # Without Plan = customers with no messages at all
    subquery_with_messages = db.query(Message.customer_id).filter(
        Message.business_id == business_id
    ).distinct()
    withoutPlanCount = db.query(Customer).filter(
        Customer.business_id == business_id,
        ~Customer.id.in_(subquery_with_messages)
    ).count()
    logger.info(f"📭 Customers without plan: {withoutPlanCount}")

    # Pending = message.status == "pending_review"
    pending = db.query(Message).filter(
        Message.business_id == business_id,
        Message.status == "pending_review"
    ).count()

    # Scheduled = message.status == "scheduled"
    scheduled = db.query(Message).filter(
        Message.business_id == business_id,
        Message.status == "scheduled"
    ).count()

    # Sent = message.sent_at is not null
    sent = db.query(Message).filter(
        Message.business_id == business_id,
        Message.sent_at.isnot(None)
    ).count()

    # Rejected = message.status == "rejected" (if used)
    rejected = db.query(Message).filter(
        Message.business_id == business_id,
        Message.status == "rejected"
    ).count()

    logger.info(f"🕓 Pending: {pending}, 📅 Scheduled: {scheduled}, ✅ Sent: {sent}, ❌ Rejected: {rejected}")

    return {
        "communitySize": communitySize,
        "withoutPlanCount": withoutPlanCount,
        "pending": pending,
        "scheduled": scheduled,
        "sent": sent,
        "rejected": rejected,
        "optedIn": optedIn,
        "optedOut": optedOut,
        "optInPending": optInPending,
        "conversations": 0,  # placeholder
    } 

def calculate_stats(business_id: int, db: Session):
    """Calculate total messages, community size, and latest consent status for the dashboard"""
    # Get total messages from messages and engagements
    total_scheduled_messages = db.query(Message).filter(
        Message.business_id == business_id,
        Message.message_type == 'scheduled'
    ).count()

    total_inbound_replies = db.query(Engagement).filter(
        Engagement.business_id == business_id,
        Engagement.response != None
    ).count()

    total_ai_responses = db.query(Engagement).filter(
        Engagement.business_id == business_id,
        Engagement.ai_response != None
    ).count()

    total_message_count = total_scheduled_messages + total_inbound_replies + total_ai_responses

    # Get community size
    community_size = db.query(Customer).filter(
        Customer.business_id == business_id,
        Customer.opted_in == True
    ).count()

    # Get latest consent status
    latest_consent_status = db.query(ConsentLog.status).filter(
        ConsentLog.business_id == business_id
    ).order_by(ConsentLog.replied_at.desc()).first()

    return {
        "total_message_count": total_message_count,
        "community_size": community_size,
        "latest_consent_status": latest_consent_status.status if latest_consent_status else None
    }

# Temporary exports for review.py import compatibility
calculate_stats = get_stats_for_business
calculate_reply_stats = lambda business_id, db: {"waitingReplies": 0, "draftsReady": 0}  # stub