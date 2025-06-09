# sys.path modifications removed
import pytest # Ensure pytest is imported
# import os # os might not be needed if PROJECT_ROOT and its usage is removed
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone

from app.services.message_service import MessageService
from app.models import (
    Message,
    Customer,
    BusinessProfile,
    RoadmapMessage,
    ConsentLog,
    OptInStatus,
    MessageTypeEnum,
    MessageStatusEnum
)
# Schemas are not directly used in service method signatures/returns shown

# Helper Fixtures
@pytest.fixture
def message_service_instance(db: Session):
    return MessageService(db=db)

# Test Cases
@pytest.mark.asyncio
async def test_create_message_success(db: Session, message_service_instance: MessageService, mock_business: BusinessProfile, mock_customer: Customer):
    # Arrange
    content = "Test message content"
    message_type = "general"
    scheduled_at = datetime.now(timezone.utc) + timedelta(days=1)

    # Act
    created_message = message_service_instance.create_message(
        customer_id=mock_customer.id,
        business_id=mock_business.id,
        content=content,
        scheduled_time=scheduled_at,
        message_type=message_type
    )

    # Assert
    assert created_message is not None
    assert created_message.id is not None
    assert created_message.content == content
    assert created_message.customer_id == mock_customer.id
    assert created_message.business_id == mock_business.id
    assert created_message.message_type == message_type
    assert created_message.status == "scheduled"
    assert created_message.scheduled_time == scheduled_at

    db_message = db.query(Message).get(created_message.id)
    assert db_message is not None
    assert db_message.content == content


@pytest.mark.asyncio
async def test_schedule_message_success_customer_opted_in(db: Session, message_service_instance: MessageService, mock_business: BusinessProfile, mock_customer: Customer):
    # Arrange
    mock_customer.opted_in = True
    db.add(mock_customer)
    db.commit()

    content = "Scheduled message content"
    scheduled_at = datetime.now(timezone.utc) + timedelta(hours=5)

    # Act
    scheduled_message = message_service_instance.schedule_message(
        customer_id=mock_customer.id,
        business_id=mock_business.id,
        content=content,
        scheduled_time=scheduled_at
    )

    # Assert
    assert scheduled_message is not None
    assert scheduled_message.message_type == "scheduled"
    assert scheduled_message.status == "scheduled"
    assert scheduled_message.content == content
    assert scheduled_message.customer_id == mock_customer.id
    assert scheduled_message.business_id == mock_business.id


@pytest.mark.asyncio
async def test_schedule_message_customer_not_opted_in(message_service_instance: MessageService, mock_business: BusinessProfile, mock_customer: Customer, db: Session):
    # Arrange
    mock_customer.opted_in = False
    db.add(mock_customer)
    db.commit()

    # Act & Assert
    with pytest.raises(ValueError, match="Customer has not opted in to receive SMS"):
        message_service_instance.schedule_message(
            customer_id=mock_customer.id,
            business_id=mock_business.id,
            content="This should not be sent",
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=1)
        )


@pytest.mark.asyncio
async def test_schedule_message_customer_not_found(message_service_instance: MessageService, mock_business: BusinessProfile):
    # Arrange
    non_existent_customer_id = 99999

    # Act & Assert
    with pytest.raises(ValueError, match="Customer has not opted in to receive SMS"):
        message_service_instance.schedule_message(
            customer_id=non_existent_customer_id,
            business_id=mock_business.id,
            content="This should not be sent either",
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=1)
        )


@pytest.mark.asyncio
async def test_get_message_by_id_found(db: Session, message_service_instance: MessageService, mock_business: BusinessProfile, mock_customer: Customer):
    # Arrange
    msg = message_service_instance.create_message(
        customer_id=mock_customer.id, business_id=mock_business.id, content="find me"
    )

    # Act
    found_message = message_service_instance.get_message(msg.id)

    # Assert
    assert found_message is not None
    assert found_message.id == msg.id
    assert found_message.content == "find me"


@pytest.mark.asyncio
async def test_get_message_by_id_not_found(message_service_instance: MessageService):
    # Arrange
    non_existent_message_id = 88888

    # Act
    found_message = message_service_instance.get_message(non_existent_message_id)

    # Assert
    assert found_message is None


@pytest.mark.asyncio
async def test_update_message_status_success(db: Session, message_service_instance: MessageService, mock_business: BusinessProfile, mock_customer: Customer):
    # Arrange
    msg = message_service_instance.create_message(
        customer_id=mock_customer.id, business_id=mock_business.id, content="status update test"
    )

    # Act
    updated_message = message_service_instance.update_message_status(msg.id, "sent")

    # Assert
    assert updated_message is not None
    assert updated_message.status == "sent"
    assert updated_message.sent_at is not None
    assert isinstance(updated_message.sent_at, datetime)
    assert (datetime.utcnow() - updated_message.sent_at).total_seconds() < 5


@pytest.mark.asyncio
async def test_update_message_status_message_not_found(message_service_instance: MessageService):
    # Arrange
    non_existent_message_id = 77777

    # Act
    result = message_service_instance.update_message_status(non_existent_message_id, "sent")

    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_get_customer_messages_all_future(db: Session, message_service_instance: MessageService, mock_business: BusinessProfile, mock_customer: Customer):
    # Arrange
    now = datetime.now(timezone.utc)
    future_sched_msg = message_service_instance.create_message(customer_id=mock_customer.id, business_id=mock_business.id, content="future sched", scheduled_time=now + timedelta(days=1))
    future_roadmap_msg = RoadmapMessage(customer_id=mock_customer.id, business_id=mock_business.id, smsContent="future roadmap", send_datetime_utc=now + timedelta(days=2), status="scheduled")
    db.add(future_roadmap_msg)

    past_sched_msg = Message(
        customer_id=mock_customer.id, business_id=mock_business.id, content="past sched",
        scheduled_time=now - timedelta(days=1), message_type="scheduled", status="scheduled"
    )
    db.add(past_sched_msg)

    past_roadmap_msg = RoadmapMessage(customer_id=mock_customer.id, business_id=mock_business.id, smsContent="past roadmap", send_datetime_utc=now - timedelta(days=2), status="sent")
    db.add(past_roadmap_msg)
    db.commit()

    # Act
    result = message_service_instance.get_customer_messages(mock_customer.id, include_past=False)

    # Assert
    assert len(result["scheduled"]) == 1
    assert result["scheduled"][0].id == future_sched_msg.id
    assert len(result["roadmap"]) == 1
    assert result["roadmap"][0].id == future_roadmap_msg.id
    assert "consent_status" in result


@pytest.mark.asyncio
async def test_get_customer_messages_include_past(db: Session, message_service_instance: MessageService, mock_business: BusinessProfile, mock_customer: Customer):
    # Arrange
    now = datetime.now(timezone.utc)
    future_sched_msg = message_service_instance.create_message(customer_id=mock_customer.id, business_id=mock_business.id, content="future sched", scheduled_time=now + timedelta(days=1))
    future_roadmap_msg = RoadmapMessage(customer_id=mock_customer.id, business_id=mock_business.id, smsContent="future roadmap", send_datetime_utc=now + timedelta(days=2), status="scheduled")
    db.add(future_roadmap_msg)

    past_sched_msg = Message(
        customer_id=mock_customer.id, business_id=mock_business.id, content="past sched for include_past test",
        scheduled_time=now - timedelta(days=1), message_type="scheduled", status="scheduled"
    )
    db.add(past_sched_msg)

    past_roadmap_msg = RoadmapMessage(customer_id=mock_customer.id, business_id=mock_business.id, smsContent="past roadmap", send_datetime_utc=now - timedelta(days=2), status="sent")
    db.add(past_roadmap_msg)
    db.commit()

    db.refresh(past_sched_msg)

    # Act
    result = message_service_instance.get_customer_messages(mock_customer.id, include_past=True)

    # Assert
    assert len(result["scheduled"]) == 2
    scheduled_ids = {m.id for m in result["scheduled"]}
    assert future_sched_msg.id in scheduled_ids
    assert past_sched_msg.id in scheduled_ids

    assert len(result["roadmap"]) == 2
    roadmap_ids = {r.id for r in result["roadmap"]}
    assert future_roadmap_msg.id in roadmap_ids
    assert past_roadmap_msg.id in roadmap_ids


@pytest.mark.asyncio
async def test_get_customer_messages_no_messages(message_service_instance: MessageService, mock_customer: Customer):
    # Act
    result = message_service_instance.get_customer_messages(mock_customer.id)

    # Assert
    assert len(result["scheduled"]) == 0
    assert len(result["roadmap"]) == 0
    assert result["consent_status"] == "pending"


@pytest.mark.asyncio
async def test_get_customer_consent_status_logic(db: Session, message_service_instance: MessageService, mock_customer: Customer):
    # Arrange
    result1 = message_service_instance.get_customer_messages(mock_customer.id)
    assert result1["consent_status"] == "pending"

    log_opt_out = ConsentLog(customer_id=mock_customer.id, status=OptInStatus.OPTED_OUT.value, replied_at=datetime.now(timezone.utc) - timedelta(days=1))
    db.add(log_opt_out)
    db.commit()
    result2 = message_service_instance.get_customer_messages(mock_customer.id)
    assert result2["consent_status"] == OptInStatus.OPTED_OUT.value

    log_opt_in = ConsentLog(customer_id=mock_customer.id, status=OptInStatus.OPTED_IN.value, replied_at=datetime.now(timezone.utc))
    db.add(log_opt_in)
    db.commit()
    result3 = message_service_instance.get_customer_messages(mock_customer.id)
    assert result3["consent_status"] == OptInStatus.OPTED_IN.value

# Final newline for PEP8