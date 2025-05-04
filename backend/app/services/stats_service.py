# backend/app/services/stats_service.py

from sqlalchemy.orm import Session
from app.models import Customer, RoadmapMessage, Message, Engagement, ConsentLog
from sqlalchemy import func, desc, distinct # Added distinct
from loguru import logger
from datetime import datetime, timedelta, timezone # Added timedelta, timezone

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
            elif latest_consent.status in ["pending", "waiting"]: # Check for multiple pending states
                optInPending += 1
            # Handle potential edge cases or assume pending if status is unexpected
            else:
                 optInPending += 1
        else:
            # No consent log means pending opt-in request
            optInPending += 1

    logger.info(f"✅ Opted In: {optedIn}, ⏳ Pending Opt-in: {optInPending}, ❌ Opted Out: {optedOut}")

    # Without Plan = customers with no messages at all (Roadmap or Scheduled)
    subquery_roadmap = db.query(RoadmapMessage.customer_id).filter(RoadmapMessage.business_id == business_id).distinct()
    subquery_scheduled = db.query(Message.customer_id).filter(Message.business_id == business_id, Message.message_type == 'scheduled').distinct()

    customers_with_plan = subquery_roadmap.union(subquery_scheduled).subquery()

    withoutPlanCount = db.query(Customer).filter(
        Customer.business_id == business_id,
        ~Customer.id.in_(customers_with_plan)
    ).count()
    logger.info(f"📭 Customers without plan: {withoutPlanCount}")


    # Pending = message.status == "pending_review" (Often 0 for outgoing, keep for potential future use)
    pending = db.query(Message).filter(
        Message.business_id == business_id,
        Message.status == "pending_review",
        Message.message_type == 'scheduled' # Ensure it's outgoing type
    ).count()

    # Scheduled = message.status == "scheduled" AND scheduled_time in the future
    now_utc = datetime.now(timezone.utc)
    scheduled = db.query(Message).filter(
        Message.business_id == business_id,
        Message.status == "scheduled",
        Message.scheduled_time != None, # Ensure time is set
        Message.scheduled_time >= now_utc # Ensure it's upcoming
    ).count()

    # Sent = message.sent_at is not null (Total historical sent)
    sent = db.query(Message).filter(
        Message.business_id == business_id,
        Message.sent_at.isnot(None)
    ).count()

    # Rejected = message.status == "rejected" (if used)
    rejected = db.query(Message).filter(
        Message.business_id == business_id,
        Message.status == "rejected"
    ).count()

    logger.info(f"🕓 Pending Outgoing: {pending}, 📅 Scheduled: {scheduled}, ✅ Sent (Total): {sent}, ❌ Rejected: {rejected}")

    # --- Calculate recent activity ---
    seven_days_ago = now_utc - timedelta(days=7)

    sent_last_7_days = db.query(Message).filter(
        Message.business_id == business_id,
        Message.sent_at != None,
        Message.sent_at >= seven_days_ago
    ).count()
    logger.info(f"📤 Sent Last 7 Days: {sent_last_7_days}")

    # Use created_at for replies as sent_at might be null until AI response is sent
    replies_last_7_days = db.query(Engagement).filter(
        Engagement.business_id == business_id,
        Engagement.response != None,
        Engagement.created_at >= seven_days_ago
    ).count()
    logger.info(f"📥 Replies Last 7 Days: {replies_last_7_days}")
    # --- End Recent Activity ---

    return {
        "communitySize": communitySize,
        "withoutPlanCount": withoutPlanCount,
        "pending": pending,
        "scheduled": scheduled,
        "sent": sent, # Total sent
        "rejected": rejected,
        "optedIn": optedIn,
        "optedOut": optedOut,
        "optInPending": optInPending,
        "conversations": 0, # placeholder - could count active Conversation records
        "sentLast7Days": sent_last_7_days,
        "repliesLast7Days": replies_last_7_days
    }

def calculate_reply_stats(business_id: int, db: Session):
    """Calculate stats related to customer replies and AI drafts."""
    logger.info(f"📊 Fetching reply stats for business_id={business_id}")

    # Drafts Ready for Review (AI generated, status='pending_review')
    drafts_query = db.query(Engagement).filter(
        Engagement.business_id == business_id,
        Engagement.status == 'pending_review',
        Engagement.ai_response != None
    )
    total_drafts = drafts_query.count()
    logger.info(f"🤖 AI Drafts Ready (Total): {total_drafts}")

    # Unique Customers Waiting (customers associated with pending drafts)
    # Use distinct() on customer_id from the same query
    customers_waiting = drafts_query.distinct(Engagement.customer_id).count()
    logger.info(f"👥 Customers with Waiting Drafts (Unique): {customers_waiting}")

    # Count of received messages (Engagements with a customer response)
    received_count = db.query(Engagement).filter(
        Engagement.business_id == business_id,
        Engagement.response != None # Count engagements initiated by customer response
    ).count()
    logger.info(f"📩 Received Messages (Total): {received_count}")

    # Map to the keys expected by the frontend API calls:
    # `/review/reply-stats/{business_id}` response -> { customers_waiting: X, messages_total: Y }
    # `/review/received-messages/{business_id}` response -> { received_count: Z }
    # We return all from this function now for simplicity if routes use it.
    return {
        "customers_waiting": customers_waiting, # Used for big number & 'Waiting' line item
        "messages_total": total_drafts,         # Used for 'AI Drafts Ready' line item
        "received_count": received_count        # Used for 'Messages Received' line item
    }


# --- Ensure these are the export lines at the bottom ---
calculate_stats = get_stats_for_business
calculate_reply_stats = calculate_reply_stats # Replace the lambda stub with this line