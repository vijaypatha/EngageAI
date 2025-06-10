# backend/app/services/inbox_service.py

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, case, text, literal_column
from app.models import Customer, Message, ConsentLog, OptInStatus
from app.schemas import InboxCustomerSummary
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime
import math

def get_paginated_inbox_summaries(
    db: Session, business_id: int, page: int, size: int
) -> Tuple[List[InboxCustomerSummary], int]:
    """
    Fetches paginated inbox summaries for a given business.
    Each summary includes customer details, last message content and timestamp,
    and a count of unread messages (currently placeholder).
    """

    # Subquery to get the latest message ID for each customer conversation
    # This assumes 'Message' table stores all communications (sent, received, AI, etc.)
    # and 'sent_at' is the definitive timestamp for ordering.
    latest_message_subquery = (
        db.query(
            Message.customer_id,
            func.max(Message.sent_at).label("latest_message_timestamp")
        )
        .filter(Message.business_id == business_id)
        .filter(Message.is_hidden == False) # Exclude hidden messages from determining the latest
        .group_by(Message.customer_id)
        .subquery("latest_customer_message_times")
    )

    # Subquery to get the actual content of the latest message using the timestamp from above
    # (or ID if timestamps are not unique enough, but sent_at should be good for latest)
    actual_latest_message_subquery = (
        db.query(
            Message.customer_id,
            Message.content.label("last_message_content"),
            Message.sent_at.label("last_message_timestamp_val") # To join on exact timestamp
        )
        .join(
            latest_message_subquery,
            (Message.customer_id == latest_message_subquery.c.customer_id) &
            (Message.sent_at == latest_message_subquery.c.latest_message_timestamp)
        )
        .filter(Message.business_id == business_id)
        .filter(Message.is_hidden == False)
         # If multiple messages can have the exact same latest timestamp for a customer,
         # we might need to add another ordering and limit(1) here, e.g., order by Message.id.desc()
         # However, func.max on sent_at in the first subquery should give one definitive time.
        .distinct(Message.customer_id) # Ensure one message per customer if multiple share the exact latest timestamp
        .subquery("actual_latest_messages")
    )

    # Subquery for the latest consent status
    latest_consent_subquery = (
        db.query(
            ConsentLog.customer_id,
            func.max(ConsentLog.created_at).label("latest_consent_created_at")
        )
        .filter(ConsentLog.business_id == business_id)
        .group_by(ConsentLog.customer_id)
        .subquery("latest_customer_consent_times")
    )

    actual_latest_consent_subquery = (
        db.query(
            ConsentLog.customer_id,
            ConsentLog.status.label("consent_status_val"),
            (ConsentLog.status == OptInStatus.OPTED_IN).label("opted_in_val")
        )
        .join(
            latest_consent_subquery,
            (ConsentLog.customer_id == latest_consent_subquery.c.customer_id) &
            (ConsentLog.created_at == latest_consent_subquery.c.latest_consent_created_at)
        )
        .filter(ConsentLog.business_id == business_id)
        .distinct(ConsentLog.customer_id) # Ensure one consent status per customer
        .subquery("actual_latest_consents")
    )

    # Main query to fetch customers and join with the latest message and consent data
    query = (
        db.query(
            Customer.id.label("customer_id"),
            Customer.customer_name,
            Customer.phone,
            actual_latest_consent_subquery.c.opted_in_val.label("opted_in"),
            actual_latest_consent_subquery.c.consent_status_val.label("consent_status"),
            actual_latest_message_subquery.c.last_message_content,
            actual_latest_message_subquery.c.last_message_timestamp_val.label("last_message_timestamp"),
            literal_column("0").label("unread_message_count"), # Placeholder for unread_message_count
            Customer.business_id
        )
        .join(Customer, Customer.business_id == business_id) # Start with Customer table, filter by business_id
        .outerjoin( # Use outerjoin in case a customer has no messages
            actual_latest_message_subquery,
            Customer.id == actual_latest_message_subquery.c.customer_id
        )
        .outerjoin( # Use outerjoin in case a customer has no consent logs (though unlikely for active customers)
            actual_latest_consent_subquery,
            Customer.id == actual_latest_consent_subquery.c.customer_id
        )
        .filter(Customer.business_id == business_id) # Ensure we only get customers for this business
    )

    # Get total count before pagination for the response
    total_count_query = query.with_entities(func.count(Customer.id).label("total_customers"))
    # The join condition for total_count_query needs to be on Customer.id if that's the distinct entity we're counting
    # However, the main query joins Customer with other subqueries.
    # A simpler way for total customers of a business:
    total_customers_for_business = db.query(func.count(Customer.id)).filter(Customer.business_id == business_id).scalar()

    if total_customers_for_business is None:
        total_customers_for_business = 0

    # Apply ordering: customers with more recent messages first, then by customer ID
    # Coalesce last_message_timestamp to a very old date for customers with no messages to sort them last.
    query = query.order_by(
        desc(func.coalesce(actual_latest_message_subquery.c.last_message_timestamp_val, datetime.min)),
        Customer.id
    )

    # Apply pagination
    offset = (page - 1) * size
    paginated_results = query.offset(offset).limit(size).all()

    # Convert results to the Pydantic schema
    # The results are SQLAlchemy Row objects, access items by label or index
    summaries = [
        InboxCustomerSummary(
            customer_id=row.customer_id,
            customer_name=row.customer_name,
            phone=row.phone,
            opted_in=row.opted_in if row.opted_in is not None else False, # Default if no consent log
            consent_status=row.consent_status if row.consent_status else OptInStatus.UNKNOWN.value, # Default
            last_message_content=row.last_message_content,
            last_message_timestamp=row.last_message_timestamp,
            unread_message_count=row.unread_message_count, # Will be 0 due to placeholder
            business_id=row.business_id,
        )
        for row in paginated_results
    ]

    return summaries, total_customers_for_business
