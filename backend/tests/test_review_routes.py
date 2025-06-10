# backend/tests/test_review_routes.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List

from app.models import BusinessProfile, Customer, Message, ConsentLog, OptInStatus, MessageTypeEnum, MessageStatusEnum
from app.schemas import PaginatedInboxSummaries, InboxCustomerSummary # Assuming these are the correct schema names

# Helper function to create test data - can be moved to conftest if used by multiple test files
def create_test_business(db: Session, name="Test Business Inc."):
    business = BusinessProfile(
        business_name=name,
        industry="Testing",
        business_goal="Write great tests",
        primary_services="Pytest and FastAPI",
        representative_name="Test Rep",
        timezone="UTC"
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    return business

def create_test_customer(db: Session, business_id: int, name: str, phone: str, opted_in: bool = True):
    customer = Customer(
        business_id=business_id,
        customer_name=name,
        phone=phone,
        lifecycle_stage="Lead",
        opted_in=opted_in, # Set the main opted_in flag
        sms_opt_in_status=OptInStatus.OPTED_IN.value if opted_in else OptInStatus.OPTED_OUT.value
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer

def create_test_message(db: Session, business_id: int, customer_id: int, content: str, sent_at: datetime, is_hidden: bool = False):
    message = Message(
        business_id=business_id,
        customer_id=customer_id,
        content=content,
        message_type=MessageTypeEnum.OUTBOUND, # Assuming outbound for simplicity in summary
        status=MessageStatusEnum.SENT,
        sent_at=sent_at,
        created_at=sent_at, # For simplicity, align created_at with sent_at
        is_hidden=is_hidden
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message

def create_test_consent_log(db: Session, business_id: int, customer_id: int, status: OptInStatus, replied_at: datetime):
    consent_log = ConsentLog(
        business_id=business_id,
        customer_id=customer_id,
        method="SMS", # Example method
        phone_number="1234567890", # Placeholder, ensure customer phone is used if needed by logic
        status=status.value,
        replied_at=replied_at,
        sent_at=replied_at - timedelta(minutes=5) # Assume sent a bit before reply
    )
    db.add(consent_log)
    db.commit()
    db.refresh(consent_log)
    return consent_log


def test_get_inbox_summaries_success_basic(test_app_client_fixture: TestClient, db: Session):
    # 1. Arrange
    business = create_test_business(db, name="Inbox Test Biz")

    customer1_time = datetime.now(timezone.utc) - timedelta(hours=1)
    customer1 = create_test_customer(db, business_id=business.id, name="Customer Alpha", phone="111000111")
    create_test_message(db, business_id=business.id, customer_id=customer1.id, content="Latest message for Alpha", sent_at=customer1_time)
    create_test_consent_log(db, business_id=business.id, customer_id=customer1.id, status=OptInStatus.OPTED_IN, replied_at=customer1_time)

    customer2_time = datetime.now(timezone.utc) - timedelta(hours=2)
    customer2 = create_test_customer(db, business_id=business.id, name="Customer Beta", phone="222000222", opted_in=False)
    create_test_message(db, business_id=business.id, customer_id=customer2.id, content="Old message for Beta", sent_at=customer2_time)
    create_test_consent_log(db, business_id=business.id, customer_id=customer2.id, status=OptInStatus.OPTED_OUT, replied_at=customer2_time)

    # Customer with no messages (should still appear if they are a customer of the business)
    customer3 = create_test_customer(db, business_id=business.id, name="Customer Gamma (No Msgs)", phone="333000333")
    create_test_consent_log(db, business_id=business.id, customer_id=customer3.id, status=OptInStatus.PENDING, replied_at=datetime.now(timezone.utc) - timedelta(hours=3))


    # 2. Act
    response = test_app_client_fixture.get(f"/review/inbox/summaries?business_id={business.id}")

    # 3. Assert
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 3
    assert data["page"] == 1
    assert data["size"] == 20 # Default size
    assert data["pages"] == 1
    assert len(data["items"]) == 3

    # Items should be ordered by last_message_timestamp desc (customer1, customer2, customer3)
    # Customer 3 (no messages) will have null last_message_timestamp, should come last.

    item1 = data["items"][0]
    assert item1["customer_name"] == "Customer Alpha"
    assert item1["last_message_content"] == "Latest message for Alpha"
    assert item1["opted_in"] is True
    assert item1["consent_status"] == OptInStatus.OPTED_IN.value
    assert item1["unread_message_count"] == 0

    item2 = data["items"][1]
    assert item2["customer_name"] == "Customer Beta"
    assert item2["last_message_content"] == "Old message for Beta"
    assert item2["opted_in"] is False
    assert item2["consent_status"] == OptInStatus.OPTED_OUT.value

    item3 = data["items"][2]
    assert item3["customer_name"] == "Customer Gamma (No Msgs)"
    assert item3["last_message_content"] is None
    assert item3["opted_in"] is False # Default from Customer model if no consent log leads to OPTED_IN
    assert item3["consent_status"] == OptInStatus.PENDING.value


def test_get_inbox_summaries_pagination(test_app_client_fixture: TestClient, db: Session):
    business = create_test_business(db, name="Pagination Test Biz")
    customers_data = []
    for i in range(25):
        cust_time = datetime.now(timezone.utc) - timedelta(minutes=i*10) # Ensure distinct timestamps for ordering
        customer = create_test_customer(db, business_id=business.id, name=f"Cust {i:02d}", phone=f"555000{i:02d}")
        create_test_message(db, business_id=business.id, customer_id=customer.id, content=f"Msg for Cust {i:02d}", sent_at=cust_time)
        create_test_consent_log(db, business_id=business.id, customer_id=customer.id, status=OptInStatus.OPTED_IN, replied_at=cust_time)
        customers_data.append({"name": f"Cust {i:02d}", "time": cust_time})

    # Page 1
    response_p1 = test_app_client_fixture.get(f"/review/inbox/summaries?business_id={business.id}&page=1&size=10")
    assert response_p1.status_code == 200
    data_p1 = response_p1.json()
    assert data_p1["total"] == 25
    assert data_p1["page"] == 1
    assert data_p1["size"] == 10
    assert data_p1["pages"] == 3
    assert len(data_p1["items"]) == 10
    assert data_p1["items"][0]["customer_name"] == "Cust 00" # Newest

    # Page 2
    response_p2 = test_app_client_fixture.get(f"/review/inbox/summaries?business_id={business.id}&page=2&size=10")
    assert response_p2.status_code == 200
    data_p2 = response_p2.json()
    assert len(data_p2["items"]) == 10
    assert data_p2["items"][0]["customer_name"] == "Cust 10"

    # Page 3 (last page)
    response_p3 = test_app_client_fixture.get(f"/review/inbox/summaries?business_id={business.id}&page=3&size=10")
    assert response_p3.status_code == 200
    data_p3 = response_p3.json()
    assert len(data_p3["items"]) == 5
    assert data_p3["items"][0]["customer_name"] == "Cust 20"

def test_get_inbox_summaries_business_with_no_customers(test_app_client_fixture: TestClient, db: Session):
    business = create_test_business(db, name="No Customer Biz")
    response = test_app_client_fixture.get(f"/review/inbox/summaries?business_id={business.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0
    assert data["pages"] == 0

def test_get_inbox_summaries_invalid_business_id(test_app_client_fixture: TestClient):
    non_existent_biz_id = 99999
    response = test_app_client_fixture.get(f"/review/inbox/summaries?business_id={non_existent_biz_id}")
    # The service currently returns empty list if business_id doesn't match any customers,
    # which is acceptable. It doesn't explicitly check if business_id itself is valid.
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0

def test_get_inbox_summaries_customer_with_hidden_message_as_last(test_app_client_fixture: TestClient, db: Session):
    business = create_test_business(db, name="Hidden Message Biz")
    customer = create_test_customer(db, business_id=business.id, name="Cust With Hidden", phone="777000777")

    visible_msg_time = datetime.now(timezone.utc) - timedelta(days=1)
    create_test_message(db, business_id=business.id, customer_id=customer.id, content="Older visible message", sent_at=visible_msg_time)

    hidden_msg_time = datetime.now(timezone.utc) # Newer but hidden
    create_test_message(db, business_id=business.id, customer_id=customer.id, content="Newer hidden message", sent_at=hidden_msg_time, is_hidden=True)

    create_test_consent_log(db, business_id=business.id, customer_id=customer.id, status=OptInStatus.OPTED_IN, replied_at=visible_msg_time)

    response = test_app_client_fixture.get(f"/review/inbox/summaries?business_id={business.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["customer_name"] == "Cust With Hidden"
    assert item["last_message_content"] == "Older visible message" # Should pick the latest *visible* message
    assert datetime.fromisoformat(item["last_message_timestamp"]).replace(tzinfo=timezone.utc) == visible_msg_time.replace(microsecond=0) # Compare tz-aware, ignoring microseconds if DB truncates

# TODO: Test for unread_message_count once implemented (currently defaults to 0)
# TODO: Test edge cases for timestamps, timezones if they become more complex.
# TODO: Test with customers having only consent logs but no messages.
# TODO: Test with customers having messages but no consent logs (should use customer.opted_in).

def test_get_inbox_summaries_customer_no_messages_but_consent(test_app_client_fixture: TestClient, db: Session):
    business = create_test_business(db, name="Consent Only Biz")
    customer = create_test_customer(db, business_id=business.id, name="Consent Only Cust", phone="888000888")
    consent_time = datetime.now(timezone.utc) - timedelta(days=1)
    create_test_consent_log(db, business_id=business.id, customer_id=customer.id, status=OptInStatus.OPTED_IN, replied_at=consent_time)

    response = test_app_client_fixture.get(f"/review/inbox/summaries?business_id={business.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["customer_name"] == "Consent Only Cust"
    assert item["last_message_content"] is None
    assert item["last_message_timestamp"] is None
    assert item["opted_in"] is True
    assert item["consent_status"] == OptInStatus.OPTED_IN.value

def test_get_inbox_summaries_customer_no_consent_log_uses_opted_in_flag(test_app_client_fixture: TestClient, db: Session):
    business = create_test_business(db, name="OptedIn Flag Biz")
    # Customer is opted_in=True, but no ConsentLog entries
    customer = create_test_customer(db, business_id=business.id, name="Flag OptedIn Cust", phone="999000999", opted_in=True)
    msg_time = datetime.now(timezone.utc) - timedelta(days=1)
    create_test_message(db, business_id=business.id, customer_id=customer.id, content="Message for Flag Cust", sent_at=msg_time)

    response = test_app_client_fixture.get(f"/review/inbox/summaries?business_id={business.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["customer_name"] == "Flag OptedIn Cust"
    assert item["opted_in"] is True # Should be True from customer.opted_in
    assert item["consent_status"] == OptInStatus.OPTED_IN.value # Service logic defaults to OPTED_IN if no log but customer.opted_in is True

def test_get_inbox_summaries_customer_no_consent_log_uses_opted_out_flag(test_app_client_fixture: TestClient, db: Session):
    business = create_test_business(db, name="OptedOut Flag Biz")
    # Customer is opted_in=False, and no ConsentLog entries
    customer = create_test_customer(db, business_id=business.id, name="Flag OptedOut Cust", phone="000000000", opted_in=False)
    msg_time = datetime.now(timezone.utc) - timedelta(days=1)
    create_test_message(db, business_id=business.id, customer_id=customer.id, content="Message for Flag Cust Out", sent_at=msg_time)

    response = test_app_client_fixture.get(f"/review/inbox/summaries?business_id={business.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["customer_name"] == "Flag OptedOut Cust"
    assert item["opted_in"] is False # Should be False from customer.opted_in
    assert item["consent_status"] == "pending" # Service logic defaults to "pending" if no log and customer.opted_in is False
