# backend/app/services/stats_service.py

from sqlalchemy.orm import Session
# MODIFIED: Import Enums from app.models
from app.models import Customer, RoadmapMessage, Message, Engagement, ConsentLog, MessageTypeEnum, MessageStatusEnum
from sqlalchemy import func, desc, distinct, select # Added select for potential subquery optimization if needed later
from loguru import logger
from datetime import datetime, timedelta, timezone

def get_stats_for_business(business_id: int, db: Session):
    logger.info(f"📊 Fetching dashboard stats for business_id={business_id}")

    # Community size = count of customers
    communitySize = db.query(Customer).filter(Customer.business_id == business_id).count()
    logger.info(f"👥 Community size: {communitySize}")

    optedIn = optedOut = optInPending = 0
    customers = db.query(Customer).filter(Customer.business_id == business_id).all()

    for customer in customers:
        latest_consent = (
            db.query(ConsentLog)
            .filter(
                ConsentLog.phone_number == customer.phone, # Assuming phone is unique enough here for consent context
                ConsentLog.business_id == business_id
                )
            .order_by(desc(ConsentLog.replied_at)) # Using replied_at as per existing logic
            .first()
        )

        if latest_consent:
            # Ensure comparison is with the actual enum values or stored string representations
            # Assuming latest_consent.status is a string like 'opted_in', 'opted_out'
            if latest_consent.status == "opted_in": # TODO: Confirm if ConsentLog.status is Enum or string. If Enum, use .value
                optedIn += 1
            elif latest_consent.status == "opted_out":
                optedOut += 1
            elif latest_consent.status in ["pending", "waiting"]:
                optInPending += 1
            else:
                 optInPending += 1 # Default to pending if status is unexpected
        else:
            optInPending += 1 # No consent log implies pending opt-in

    logger.info(f"✅ Opted In: {optedIn}, ⏳ Pending Opt-in: {optInPending}, ❌ Opted Out: {optedOut}")

    # Without Plan = customers with no messages at all (Roadmap or Scheduled)
    subquery_roadmap = db.query(RoadmapMessage.customer_id).filter(RoadmapMessage.business_id == business_id).distinct()
    # MODIFIED: Use MessageTypeEnum for message_type
    subquery_scheduled = db.query(Message.customer_id).filter(
        Message.business_id == business_id,
        Message.message_type == MessageTypeEnum.SCHEDULED_MESSAGE # Use Enum member
    ).distinct()

    customers_with_plan = subquery_roadmap.union(subquery_scheduled).subquery()
    # The SAWarning about coercing Subquery can be addressed later if needed, focus on AttributeError first.
    # For example, by using: select(customers_with_plan.c.customer_id)
    withoutPlanCount = db.query(Customer).filter(
        Customer.business_id == business_id,
        ~Customer.id.in_(customers_with_plan) # SAWarning: Coercing Subquery object into a select()
    ).count()
    logger.info(f"📭 Customers without plan: {withoutPlanCount}")

    # REMOVED: 'pending' stat calculation for outgoing messages.
    # Frontend (page.tsx) has removed its usage for outgoing "pending_review" messages.
    # "pending_review" is not a standard status in MessageStatusEnum for Message objects.

    now_utc = datetime.now(timezone.utc)
    # Scheduled = message.status == "scheduled" AND scheduled_send_at in the future
    scheduled = db.query(Message).filter(
        Message.business_id == business_id,
        Message.status == MessageStatusEnum.SCHEDULED,      # MODIFIED: Use Enum member
        Message.scheduled_send_at != None,                  # MODIFIED: Correct attribute name
        Message.scheduled_send_at >= now_utc                # MODIFIED: Correct attribute name
    ).count()

    # Sent = message.sent_at is not null (Total historical sent)
    sent = db.query(Message).filter(
        Message.business_id == business_id,
        Message.sent_at.isnot(None)
    ).count()

    # Rejected = message.status == "rejected"
    # NOTE: 'REJECTED' is not a standard member of MessageStatusEnum as per message_service.py's GlobalMessageStatusEnum.
    # If 'rejected' is a custom string status, this query is okay. Otherwise, this count might be inaccurate.
    # The frontend expects this 'rejected' stat.
    rejected = db.query(Message).filter(
        Message.business_id == business_id,
        Message.status == "rejected" # Kept as string; use MessageStatusEnum.REJECTED if it exists and is appropriate.
    ).count()

    logger.info(f"📅 Scheduled (Upcoming): {scheduled}, ✅ Sent (Total): {sent}, ❌ Rejected: {rejected}")


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
        Engagement.response != None, # Customer's message/reply to the business
        Engagement.created_at >= seven_days_ago
    ).count()
    logger.info(f"📥 Replies Last 7 Days: {replies_last_7_days}")
    # --- End Recent Activity ---

    return {
        "communitySize": communitySize,
        "withoutPlanCount": withoutPlanCount,
        # "pending": pending, // REMOVED
        "scheduled": scheduled,
        "sent": sent,
        "rejected": rejected,
        "optedIn": optedIn,
        "optedOut": optedOut,
        "optInPending": optInPending,
        "conversations": 0, # Placeholder, as per existing code
        "sentLast7Days": sent_last_7_days,
        "repliesLast7Days": replies_last_7_days
    }

def calculate_reply_stats(business_id: int, db: Session):
    """Calculate stats related to customer replies and AI drafts."""
    logger.info(f"📊 Fetching reply stats for business_id={business_id}")

    # Drafts Ready for Review (AI generated, status='pending_review')
    # NOTE: Engagement.status == 'pending_review' is used here. Ensure 'pending_review' is a valid status for Engagement.
    # If Engagement.status is an Enum, use Enum member for comparison.
    drafts_query = db.query(Engagement).filter(
        Engagement.business_id == business_id,
        Engagement.status == 'pending_review', # Check if Engagement.status is an Enum
        Engagement.ai_response != None
    )
    total_drafts = drafts_query.count()
    logger.info(f"🤖 AI Drafts Ready (Total): {total_drafts}")

    customers_waiting = drafts_query.distinct(Engagement.customer_id).count()
    logger.info(f"👥 Customers with Waiting Drafts (Unique): {customers_waiting}")

    # Count of received messages (Engagements with a customer response)
    received_count = db.query(Engagement).filter(
        Engagement.business_id == business_id,
        Engagement.response != None
    ).count()
    logger.info(f"📩 Received Messages (Total Inbound): {received_count}")

    return {
        "customers_waiting": customers_waiting,
        "messages_total": total_drafts, # Corresponds to draftsReady in frontend
        "received_count": received_count
    }

# Ensure these are the export lines at the bottom
calculate_stats = get_stats_for_business
# calculate_reply_stats = calculate_reply_stats # This was redundant if function name matches