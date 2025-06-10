# backend/tests/test_customer_routes.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List
import uuid

from app.models import BusinessProfile, Customer, Message, ConsentLog, OptInStatus, MessageTypeEnum, MessageStatusEnum, Tag, CustomerTag
from app.schemas import (
    CustomerConversation, ConversationMessageForTimeline,
    Customer as CustomerSchema, CustomerSummarySchema, TagRead
)
from pydantic import parse_obj_as # For validating list of schemas

# Helper function from conftest or defined locally if needed
# For now, assuming conftest.py provides create_test_business and create_test_customer,
# or we create them here.
# Let's re-define minimal versions here for clarity if not directly importing from another test file.

def create_test_business_for_customer_tests(db: Session, name="Test Business for Customer Routes"):
    business = BusinessProfile(
        business_name=name, industry="Testing", business_goal="Customer Route Tests",
        primary_services="Testing", representative_name="Test Rep", timezone="UTC"
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    return business

def create_test_customer_for_customer_tests(db: Session, business_id: int, name: str, phone: str):
    customer = Customer(
        business_id=business_id, customer_name=name, phone=phone,
        lifecycle_stage="Contact", opted_in=True, sms_opt_in_status=OptInStatus.OPTED_IN.value
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer

def create_test_message_for_customer_tests(db: Session, business_id: int, customer_id: int, content: str, created_at: datetime, message_type=MessageTypeEnum.OUTBOUND, status=MessageStatusEnum.SENT):
    # Generate a unique conversation_id if not provided, or fetch existing one
    # For simplicity, we'll create a new one or assume it's handled by service logic if Message requires it.
    # Here, we might not even need a real conversation_id for testing this specific endpoint if it's not validated/used by it.
    # The Message model has conversation_id as nullable for now based on schema, but if it's not, this needs adjustment.

    # Check if conversation_id is required by the model or can be None
    # For now, let's assume it can be None or is not strictly checked at model level for this test scenario

    message = Message(
        business_id=business_id,
        customer_id=customer_id,
        content=content,
        message_type=message_type,
        status=status,
        created_at=created_at, # Explicitly set created_at for ordering tests
        sent_at=created_at if status == MessageStatusEnum.SENT else None,
        is_hidden=False
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def test_get_customer_conversation_success(test_app_client_fixture: TestClient, db: Session):
    # 1. Arrange
    test_business = create_test_business_for_customer_tests(db)
    test_customer = create_test_customer_for_customer_tests(db, business_id=test_business.id, name="Cust With Convo", phone="123450001")

    time1 = datetime.now(timezone.utc) - timedelta(minutes=10)
    time2 = datetime.now(timezone.utc) - timedelta(minutes=5)
    time3 = datetime.now(timezone.utc)

    msg1 = create_test_message_for_customer_tests(db, business_id=test_business.id, customer_id=test_customer.id, content="First message", created_at=time1)
    msg2 = create_test_message_for_customer_tests(db, business_id=test_business.id, customer_id=test_customer.id, content="Second message (reply)", created_at=time2, message_type=MessageTypeEnum.INBOUND, status=MessageStatusEnum.RECEIVED)
    msg3 = create_test_message_for_customer_tests(db, business_id=test_business.id, customer_id=test_customer.id, content="Third message", created_at=time3)

    # Create a message for another customer to ensure filtering
    other_customer = create_test_customer_for_customer_tests(db, business_id=test_business.id, name="Other Cust", phone="123450002")
    create_test_message_for_customer_tests(db, business_id=test_business.id, customer_id=other_customer.id, content="Other customer's message", created_at=time1)

    # 2. Act
    response = test_app_client_fixture.get(f"/customers/{test_customer.id}/conversation")

    # 3. Assert
    assert response.status_code == 200
    data = response.json()

    assert data["customer_id"] == test_customer.id
    assert len(data["messages"]) == 3

    # Validate schema of messages using Pydantic's parse_obj_as or by checking fields
    # For simplicity, checking key fields and order here.
    # In a real scenario, using parse_obj_as(List[ConversationMessageForTimeline], data["messages"]) is good.

    assert data["messages"][0]["id"] == msg1.id
    assert data["messages"][0]["content"] == "First message"
    assert data["messages"][0]["message_type"] == MessageTypeEnum.OUTBOUND.value # Default in helper

    assert data["messages"][1]["id"] == msg2.id
    assert data["messages"][1]["content"] == "Second message (reply)"
    assert data["messages"][1]["message_type"] == MessageTypeEnum.INBOUND.value

    assert data["messages"][2]["id"] == msg3.id
    assert data["messages"][2]["content"] == "Third message"

    # Check timestamps for ordering (ensure they are ISO format strings)
    assert datetime.fromisoformat(data["messages"][0]["created_at"]) == time1.replace(microsecond=0) # DB might truncate microseconds
    assert datetime.fromisoformat(data["messages"][1]["created_at"]) == time2.replace(microsecond=0)
    assert datetime.fromisoformat(data["messages"][2]["created_at"]) == time3.replace(microsecond=0)


def test_get_customer_conversation_no_messages(test_app_client_fixture: TestClient, db: Session):
    # 1. Arrange
    test_business = create_test_business_for_customer_tests(db, name="Biz NoMsg")
    test_customer = create_test_customer_for_customer_tests(db, business_id=test_business.id, name="Cust NoMsg", phone="123450003")

    # 2. Act
    response = test_app_client_fixture.get(f"/customers/{test_customer.id}/conversation")

    # 3. Assert
    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == test_customer.id
    assert len(data["messages"]) == 0

def test_get_customer_conversation_customer_not_found(test_app_client_fixture: TestClient, db: Session):
    # 1. Arrange
    non_existent_customer_id = 99999

    # 2. Act
    response = test_app_client_fixture.get(f"/customers/{non_existent_customer_id}/conversation")

    # 3. Assert
    # The route first calls the service, which queries messages. If no messages, it then checks if customer exists.
    # If customer doesn't exist, it raises 404.
    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found"


def test_get_customer_conversation_message_ordering(test_app_client_fixture: TestClient, db: Session):
    # 1. Arrange
    test_business = create_test_business_for_customer_tests(db, name="Biz OrderTest")
    test_customer = create_test_customer_for_customer_tests(db, business_id=test_business.id, name="Cust OrderTest", phone="123450004")

    time_now = datetime.now(timezone.utc)
    msg2_time = time_now - timedelta(minutes=5)
    msg1_time = time_now - timedelta(minutes=10)
    msg3_time = time_now

    # Create messages out of order by time
    msg_b = create_test_message_for_customer_tests(db, business_id=test_business.id, customer_id=test_customer.id, content="Message B (middle)", created_at=msg2_time)
    msg_a = create_test_message_for_customer_tests(db, business_id=test_business.id, customer_id=test_customer.id, content="Message A (oldest)", created_at=msg1_time)
    msg_c = create_test_message_for_customer_tests(db, business_id=test_business.id, customer_id=test_customer.id, content="Message C (newest)", created_at=msg3_time)

    # 2. Act
    response = test_app_client_fixture.get(f"/customers/{test_customer.id}/conversation")

    # 3. Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data["messages"]) == 3
    assert data["messages"][0]["content"] == "Message A (oldest)"
    assert data["messages"][0]["id"] == msg_a.id
    assert data["messages"][1]["content"] == "Message B (middle)"
    assert data["messages"][1]["id"] == msg_b.id
    assert data["messages"][2]["content"] == "Message C (newest)"
    assert data["messages"][2]["id"] == msg_c.id


# --- Tests for get_customers_by_business ---

def create_test_tag_for_customer_tests(db: Session, business_id: int, name: str):
    tag = Tag(business_id=business_id, name=name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag

def associate_tag_with_customer_for_tests(db: Session, customer_id: int, tag_id: int):
    customer_tag = CustomerTag(customer_id=customer_id, tag_id=tag_id)
    db.add(customer_tag)
    db.commit()
    # No direct refresh needed for association table entry unless it has its own attributes to load

def create_consent_log_for_customer_tests(db: Session, business_id: int, customer_id: int, status: OptInStatus, replied_at: datetime):
    consent_log = ConsentLog(
        business_id=business_id,
        customer_id=customer_id,
        method="SMS",
        phone_number="123", # Placeholder, actual customer phone used by service
        status=status.value,
        replied_at=replied_at,
        sent_at=replied_at - timedelta(minutes=2)
    )
    db.add(consent_log)
    db.commit()
    db.refresh(consent_log)
    return consent_log

def test_get_customers_by_business_success_and_schema(test_app_client_fixture: TestClient, db: Session):
    # 1. Arrange
    business = create_test_business_for_customer_tests(db, name="Business For Summary Test")

    # Customer 1: No logs, opted_in = True
    cust1 = create_test_customer_for_customer_tests(db, business_id=business.id, name="Cust1 Summary", phone="sum001")
    cust1.opted_in = True
    db.commit()

    # Customer 2: Logs, latest opted_out
    cust2 = create_test_customer_for_customer_tests(db, business_id=business.id, name="Cust2 Summary", phone="sum002")
    create_consent_log_for_customer_tests(db, business_id=business.id, customer_id=cust2.id, status=OptInStatus.OPTED_IN, replied_at=datetime.now(timezone.utc) - timedelta(days=2))
    cust2_consent_time = datetime.now(timezone.utc) - timedelta(days=1)
    create_consent_log_for_customer_tests(db, business_id=business.id, customer_id=cust2.id, status=OptInStatus.OPTED_OUT, replied_at=cust2_consent_time)

    # Customer 3: Belongs to another business
    other_biz = create_test_business_for_customer_tests(db, name="OtherBizForSummary")
    create_test_customer_for_customer_tests(db, business_id=other_biz.id, name="Cust OtherBiz", phone="sum003")

    # 2. Act
    response = test_app_client_fixture.get(f"/customers/by-business/{business.id}")

    # 3. Assert
    assert response.status_code == 200
    data = response.json()

    # Validate with Pydantic
    parsed_items = parse_obj_as(List[CustomerSummarySchema], data)
    assert len(parsed_items) == 2 # Only cust1 and cust2 should be returned

    cust1_data = next((c for c in parsed_items if c.id == cust1.id), None)
    assert cust1_data is not None
    assert cust1_data.customer_name == "Cust1 Summary"
    assert cust1_data.opted_in is True # Based on customer.opted_in as no logs directly imply this for cust1
    assert cust1_data.latest_consent_status is None # No logs for cust1
    assert cust1_data.tags == []

    cust2_data = next((c for c in parsed_items if c.id == cust2.id), None)
    assert cust2_data is not None
    assert cust2_data.customer_name == "Cust2 Summary"
    assert cust2_data.opted_in is False # Derived from latest_consent_status
    assert cust2_data.latest_consent_status == OptInStatus.OPTED_OUT.value
    assert datetime.fromisoformat(cust2_data.latest_consent_updated.replace("Z", "+00:00")) == cust2_consent_time.replace(microsecond=0)


def test_get_customers_by_business_with_tag_filter_and_consent(test_app_client_fixture: TestClient, db: Session):
    # 1. Arrange
    business = create_test_business_for_customer_tests(db, name="Biz TagFilter Summary")

    tag_common = create_test_tag_for_customer_tests(db, business_id=business.id, name="common")
    tag_specific = create_test_tag_for_customer_tests(db, business_id=business.id, name="specific")

    # Customer 1: Has 'common' tag, opted_in by log
    cust1 = create_test_customer_for_customer_tests(db, business_id=business.id, name="Tagged Cust1", phone="tag001")
    associate_tag_with_customer_for_tests(db, customer_id=cust1.id, tag_id=tag_common.id)
    create_consent_log_for_customer_tests(db, business_id=business.id, customer_id=cust1.id, status=OptInStatus.OPTED_IN, replied_at=datetime.now(timezone.utc))

    # Customer 2: Has 'common' and 'specific' tags, opted_out by log
    cust2 = create_test_customer_for_customer_tests(db, business_id=business.id, name="Tagged Cust2", phone="tag002")
    associate_tag_with_customer_for_tests(db, customer_id=cust2.id, tag_id=tag_common.id)
    associate_tag_with_customer_for_tests(db, customer_id=cust2.id, tag_id=tag_specific.id)
    create_consent_log_for_customer_tests(db, business_id=business.id, customer_id=cust2.id, status=OptInStatus.OPTED_OUT, replied_at=datetime.now(timezone.utc))

    # Customer 3: Has only 'specific' tag
    cust3 = create_test_customer_for_customer_tests(db, business_id=business.id, name="Tagged Cust3", phone="tag003")
    associate_tag_with_customer_for_tests(db, customer_id=cust3.id, tag_id=tag_specific.id)
    create_consent_log_for_customer_tests(db, business_id=business.id, customer_id=cust3.id, status=OptInStatus.PENDING, replied_at=datetime.now(timezone.utc))

    # 2. Act: Filter by 'common' tag
    response = test_app_client_fixture.get(f"/customers/by-business/{business.id}?tags=common")

    # 3. Assert
    assert response.status_code == 200
    data = parse_obj_as(List[CustomerSummarySchema], response.json())

    assert len(data) == 2 # cust1 and cust2 have 'common' tag
    customer_ids_in_response = {c.id for c in data}
    assert cust1.id in customer_ids_in_response
    assert cust2.id in customer_ids_in_response
    assert cust3.id not in customer_ids_in_response

    cust1_data = next(c for c in data if c.id == cust1.id)
    assert cust1_data.opted_in is True
    assert cust1_data.latest_consent_status == OptInStatus.OPTED_IN.value
    assert len(cust1_data.tags) == 1
    assert cust1_data.tags[0].name == "common"

    # Act: Filter by 'common' AND 'specific' tags
    response_multi_tag = test_app_client_fixture.get(f"/customers/by-business/{business.id}?tags=common,specific")
    assert response_multi_tag.status_code == 200
    data_multi_tag = parse_obj_as(List[CustomerSummarySchema], response_multi_tag.json())

    assert len(data_multi_tag) == 1 # Only cust2 has both 'common' and 'specific'
    assert data_multi_tag[0].id == cust2.id
    cust2_data = data_multi_tag[0]
    assert cust2_data.opted_in is False
    assert cust2_data.latest_consent_status == OptInStatus.OPTED_OUT.value
    assert len(cust2_data.tags) == 2 # Should have both tags


def test_get_customers_by_business_no_customers(test_app_client_fixture: TestClient, db: Session):
    business = create_test_business_for_customer_tests(db, name="Empty Biz")
    response = test_app_client_fixture.get(f"/customers/by-business/{business.id}")
    assert response.status_code == 200
    data = parse_obj_as(List[CustomerSummarySchema], response.json())
    assert len(data) == 0

def test_get_customers_by_business_non_existent_biz_id(test_app_client_fixture: TestClient, db: Session):
    response = test_app_client_fixture.get(f"/customers/by-business/99999")
    assert response.status_code == 200 # Current behavior is to return empty list
    data = parse_obj_as(List[CustomerSummarySchema], response.json())
    assert len(data) == 0
