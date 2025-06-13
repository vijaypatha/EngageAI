# backend/app/services/inbox_service.py

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, case, text, literal_column
from app.models import Customer, Message, ConsentLog, OptInStatus, MessageTypeEnum # Import MessageTypeEnum
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
    and a count of unread messages.
    """

    # Subquery to get the latest message ID and timestamp for each customer conversation
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
    actual_latest_message_subquery = (
        db.query(
            Message.customer_id,
            Message.content.label("last_message_content"),
            Message.sent_at.label("last_message_timestamp_val")
        )
        .join(
            latest_message_subquery,
            (Message.customer_id == latest_message_subquery.c.customer_id) &
            (Message.sent_at == latest_message_subquery.c.latest_message_timestamp)
        )
        .filter(Message.business_id == business_id)
        .filter(Message.is_hidden == False)
        .distinct(Message.customer_id)
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
            (ConsentLog.status == OptInStatus.OPTED_IN.value).label("opted_in_val") # Use .value for comparison
        )
        .join(
            latest_consent_subquery,
            (ConsentLog.customer_id == latest_consent_subquery.c.customer_id) &
            (ConsentLog.created_at == latest_consent_subquery.c.latest_consent_created_at)
        )
        .filter(ConsentLog.business_id == business_id)
        .distinct(ConsentLog.customer_id)
        .subquery("actual_latest_consents")
    )

    # Subquery to calculate unread message count
    # Count inbound messages where sent_at is after customer.last_read_at
    unread_count_subquery = (
        db.query(
            Message.customer_id,
            func.count(Message.id).label("unread_messages")
        )
        .join(Customer, Message.customer_id == Customer.id)
        .filter(
            Message.business_id == business_id,
            Message.message_type == MessageTypeEnum.INBOUND.value, # Only count inbound as unread
            Message.is_hidden == False,
            # Only count if message was sent after customer's last_read_at (or if last_read_at is NULL, all are unread)
            (Message.sent_at > Customer.last_read_at) | (Customer.last_read_at.is_(None))
        )
        .group_by(Message.customer_id)
        .subquery("unread_message_counts")
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
            unread_count_subquery.c.unread_messages.label("unread_message_count"), # Use calculated unread count
            Customer.business_id
        )
        .filter(Customer.business_id == business_id) # Start with Customer table, filter by business_id
        .outerjoin( # Use outerjoin in case a customer has no messages
            actual_latest_message_subquery,
            Customer.id == actual_latest_message_subquery.c.customer_id
        )
        .outerjoin( # Use outerjoin in case a customer has no consent logs
            actual_latest_consent_subquery,
            Customer.id == actual_latest_consent_subquery.c.customer_id
        )
        .outerjoin( # Outer join with unread count subquery
            unread_count_subquery,
            Customer.id == unread_count_subquery.c.customer_id
        )
    )

    # Get total count before pagination
    total_customers_for_business = db.query(func.count(Customer.id)).filter(Customer.business_id == business_id).scalar()

    if total_customers_for_business is None:
        total_customers_for_business = 0

    # Apply ordering: customers with more recent messages first, then by customer ID
    # Coalesce last_message_timestamp to a very old date for customers with no messages to sort them last.
    # Order by unread count (descending) first, then by last message timestamp (descending)
    query = query.order_by(
        desc(func.coalesce(unread_count_subquery.c.unread_messages, 0)), # Unread messages first
        desc(func.coalesce(actual_latest_message_subquery.c.last_message_timestamp_val, datetime.min)),
        Customer.id
    )

    # Apply pagination
    offset = (page - 1) * size
    paginated_results = query.offset(offset).limit(size).all()

    # Convert results to the Pydantic schema
    summaries = []
    for row in paginated_results:
        summary = InboxCustomerSummary(
            customer_id=row.customer_id,
            customer_name=row.customer_name,
            phone=row.phone,
            # If no consent log, default opted_in to False and consent_status to NOT_SET or PENDING
            opted_in=row.opted_in if row.opted_in is not None else False,
            consent_status=row.consent_status if row.consent_status else OptInStatus.NOT_SET.value, # Default if no consent log
            last_message_content=row.last_message_content,
            last_message_timestamp=row.last_message_timestamp,
            unread_message_count=row.unread_message_count if row.unread_message_count is not None else 0, # Default to 0 if NULL
            business_id=row.business_id,
            # is_unread will now be derived from unread_message_count on the frontend if needed
            is_unread=row.unread_message_count > 0 if row.unread_message_count is not None else False, # Explicitly set for backward comp.
        )
        summaries.append(summary)

    return summaries, total_customers_for_business