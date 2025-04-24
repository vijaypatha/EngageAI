import pytest
from datetime import datetime, timedelta, timezone
from app.services.message_service import MessageService, MessageStatus
from app.models import RoadmapMessage, ScheduledSMS, Customer, ConsentLog

@pytest.fixture
def message_service(db_session):
    return MessageService(db_session)

@pytest.fixture
def customer(db_session):
    customer = Customer(
        customer_name="Test Customer",
        business_id=1,
        opted_in=True
    )
    db_session.add(customer)
    db_session.commit()
    return customer

@pytest.fixture
def roadmap_message(db_session, customer):
    message = RoadmapMessage(
        customer_id=customer.id,
        business_id=1,
        smsContent="Test message",
        send_datetime_utc=datetime.now(timezone.utc),
        status=MessageStatus.PENDING.value
    )
    db_session.add(message)
    db_session.commit()
    return message

def test_get_customer_messages(message_service, customer, roadmap_message):
    result = message_service.get_customer_messages(customer.id)
    assert len(result["roadmap"]) == 1
    assert len(result["scheduled"]) == 0
    assert result["consent_status"] == "pending"

def test_schedule_message_success(message_service, customer, roadmap_message):
    result = message_service.schedule_message(roadmap_message.id)
    assert result["status"] == "scheduled"
    assert "scheduled_sms_id" in result
    assert result["details"]["customer_name"] == customer.customer_name
    assert result["details"]["smsContent"] == roadmap_message.smsContent
    assert result["details"]["status"] == MessageStatus.SCHEDULED.value

def test_schedule_message_already_scheduled(message_service, customer, roadmap_message, db_session):
    # First schedule
    message_service.schedule_message(roadmap_message.id)
    # Try scheduling again
    result = message_service.schedule_message(roadmap_message.id)
    assert result["status"] == "already scheduled"

def test_schedule_message_invalid_id(message_service):
    with pytest.raises(ValueError, match="Roadmap message not found"):
        message_service.schedule_message(999)

def test_schedule_message_customer_not_opted_in(message_service, customer, roadmap_message, db_session):
    customer.opted_in = False
    db_session.commit()
    with pytest.raises(ValueError, match="Customer has not opted in to receive SMS"):
        message_service.schedule_message(roadmap_message.id)

def test_get_customer_consent_status_with_log(message_service, customer, db_session):
    consent_log = ConsentLog(
        customer_id=customer.id,
        status="approved",
        replied_at=datetime.now(timezone.utc)
    )
    db_session.add(consent_log)
    db_session.commit()
    status = message_service._get_customer_consent_status(customer.id)
    assert status == "approved"

def test_get_customer_consent_status_no_log(message_service, customer):
    status = message_service._get_customer_consent_status(customer.id)
    assert status == "pending"

def test_format_scheduled_message(message_service, customer):
    scheduled_sms = ScheduledSMS(
        id=1,
        customer_id=customer.id,
        business_id=1,
        message="Test scheduled message",
        send_time=datetime.now(timezone.utc),
        status=MessageStatus.SCHEDULED.value,
        source="roadmap"
    )
    formatted = message_service._format_scheduled_message(scheduled_sms, customer)
    assert formatted["id"] == scheduled_sms.id
    assert formatted["customer_name"] == customer.customer_name
    assert formatted["smsContent"] == scheduled_sms.message
    assert formatted["status"] == MessageStatus.SCHEDULED.value
    assert formatted["source"] == "scheduled"
    assert "send_datetime_utc" in formatted

# Add more tests for each method... 