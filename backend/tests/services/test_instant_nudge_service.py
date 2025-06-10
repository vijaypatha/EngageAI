import pytest
from sqlalchemy.orm import Session
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta
import os
import json
import uuid
import pytz
from typing import Any, List, Dict
from fastapi import HTTPException, status # Added status

from app.services.instant_nudge_service import generate_instant_nudge, handle_instant_nudge_batch
from app.models import BusinessProfile, Customer, Message, Conversation, MessageStatusEnum, MessageTypeEnum, Engagement
from app.schemas import PlanMessage
from app.config import settings
from app.celery_tasks import process_scheduled_message_task
from app.services.twilio_service import TwilioService

# Assuming conftest.py provides:
# - db: Session fixture
# - mock_business: BusinessProfile ORM instance fixture
# - mock_customer: Customer ORM instance fixture

@pytest.fixture
def customer1(db: Session, mock_business: BusinessProfile):
    phone_number = "+15551230001"
    cust = db.query(Customer).filter(Customer.phone == phone_number, Customer.business_id == mock_business.id).first()
    if cust:
        if not cust.opted_in: cust.opted_in = True; db.commit(); db.refresh(cust)
        return cust
    cust = Customer(id=101, business_id=mock_business.id, customer_name="Cust One Instant", phone=phone_number, opted_in=True)
    db.add(cust); db.commit(); db.refresh(cust)
    return cust

@pytest.fixture
def customer2(db: Session, mock_business: BusinessProfile):
    phone_number = "+15551230002"
    cust = db.query(Customer).filter(Customer.phone == phone_number, Customer.business_id == mock_business.id).first()
    if cust:
        if not cust.opted_in: cust.opted_in = True; db.commit(); db.refresh(cust)
        return cust
    cust = Customer(id=102, business_id=mock_business.id, customer_name="Cust Two Instant", phone=phone_number, opted_in=True)
    db.add(cust); db.commit(); db.refresh(cust)
    return cust

@pytest.fixture
def mock_openai_client_for_instant_nudge():
    with patch('os.getenv', return_value="sk-dummykey"), \
         patch('app.services.instant_nudge_service.openai.OpenAI') as mock_openai_constructor:
        mock_instance = MagicMock()
        mock_openai_constructor.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_style_service_get_guide():
    with patch('app.services.instant_nudge_service.get_style_guide', new_callable=AsyncMock) as mock_get_style:
        mock_get_style.return_value = {
            "key_phrases": ["Welcome!", "Special offer"],
            "message_patterns": {"patterns": ["Pattern A", "Pattern B"]},
            "personality_traits": ["friendly", "helpful"],
            "special_elements": {"emojis": ["😊", "🎉"]},
            "style_notes": {"notes": "Be concise."}
        }
        yield mock_get_style

# --- Tests for generate_instant_nudge ---
@pytest.mark.asyncio
async def test_generate_instant_nudge_success(
    db: Session, mock_business: BusinessProfile, mock_openai_client_for_instant_nudge, mock_style_service_get_guide
):
    topic = "New Product Launch"
    expected_ai_message = "Hi {customer_name}, check out our new product! - Test Rep"
    mock_openai_client_for_instant_nudge.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=expected_ai_message))]
    )
    result = await generate_instant_nudge(topic, mock_business.id, db)
    assert result["message"] == expected_ai_message
    mock_openai_client_for_instant_nudge.chat.completions.create.assert_called_once()
    call_args, called_kwargs = mock_openai_client_for_instant_nudge.chat.completions.create.call_args
    user_prompt = called_kwargs['messages'][1]['content']
    assert topic in user_prompt
    assert mock_business.business_name in user_prompt
    assert "Welcome!" in user_prompt

@pytest.mark.asyncio
async def test_generate_instant_nudge_missing_placeholder_fix(
    db: Session, mock_business: BusinessProfile, mock_openai_client_for_instant_nudge, mock_style_service_get_guide
):
    topic = "Reminder"
    ai_message_without_placeholder = "Just a friendly reminder. - Test Rep"
    expected_fixed_message = f"Hi {{customer_name}}, {ai_message_without_placeholder}"
    mock_openai_client_for_instant_nudge.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=ai_message_without_placeholder))]
    )
    result = await generate_instant_nudge(topic, mock_business.id, db)
    assert result["message"] == expected_fixed_message

@pytest.mark.asyncio
async def test_generate_instant_nudge_business_not_found(db: Session, mock_openai_client_for_instant_nudge, mock_style_service_get_guide):
    with pytest.raises(ValueError, match="Business not found for ID: 999"):
        await generate_instant_nudge("Test Topic", 999, db)

@pytest.mark.asyncio
async def test_generate_instant_nudge_openai_api_error(
    db: Session, mock_business: BusinessProfile, mock_openai_client_for_instant_nudge, mock_style_service_get_guide
):
    mock_openai_client_for_instant_nudge.chat.completions.create.side_effect = Exception("OpenAI API Down")
    with pytest.raises(Exception, match="AI message generation failed: OpenAI API Down"):
        await generate_instant_nudge("Test Topic", mock_business.id, db)

# --- Tests for handle_instant_nudge_batch ---
@pytest.mark.asyncio
async def test_handle_instant_nudge_batch_send_immediately_success(
    db: Session, mock_business: BusinessProfile, customer1: Customer, customer2: Customer
):
    message_content_template = "Hi {customer_name}, this is an instant nudge!"
    customer_ids = [customer1.id, customer2.id]
    mock_twilio_service_instance = MagicMock(spec=TwilioService)
    mock_twilio_service_instance.send_sms = AsyncMock(return_value="SMmocksendimmediately")

    with patch('app.services.instant_nudge_service.TwilioService', return_value=mock_twilio_service_instance) as MockTwilioService, \
         patch('app.services.instant_nudge_service.datetime') as mock_datetime:
        mock_now = datetime.now(timezone.utc)
        mock_datetime.now.return_value = mock_now
        result = await handle_instant_nudge_batch(
            db, mock_business.id, customer_ids, message_content_template, send_datetime_iso=None
        )
    assert result["sent_count"] == 2
    assert result["scheduled_count"] == 0
    assert result["failed_count"] == 0
    assert len(result["processed_message_ids"]) == 2
    MockTwilioService.assert_called_once_with(db)
    assert mock_twilio_service_instance.send_sms.call_count == 2
    calls = mock_twilio_service_instance.send_sms.call_args_list
    kwargs_c1 = calls[0].kwargs
    assert kwargs_c1['to'] == customer1.phone and "Cust One Instant" in kwargs_c1['message_body']
    kwargs_c2 = calls[1].kwargs
    assert kwargs_c2['to'] == customer2.phone and "Cust Two Instant" in kwargs_c2['message_body']

    messages = db.query(Message).filter(Message.customer_id.in_(customer_ids)).all()
    assert len(messages) == 2
    for msg in messages:
        assert msg.status == MessageStatusEnum.SENT.value
        assert msg.message_type == MessageTypeEnum.SCHEDULED.value
        assert msg.sent_at is not None
        sent_at_aware = msg.sent_at.replace(tzinfo=timezone.utc) if msg.sent_at.tzinfo is None else msg.sent_at.astimezone(timezone.utc)
        assert (mock_now - sent_at_aware).total_seconds() < 5
        engagement = db.query(Engagement).filter(Engagement.message_id == msg.id).first()
        assert engagement is not None and engagement.status == "sent"

@pytest.mark.asyncio
async def test_handle_instant_nudge_batch_schedule_success(
    db: Session, mock_business: BusinessProfile, customer1: Customer
):
    message_content_template = "Hi {customer_name}, this is a scheduled nudge!"
    customer_ids = [customer1.id]
    now_utc = datetime.now(pytz.utc)
    future_datetime = now_utc + timedelta(hours=2)
    send_datetime_iso_str = future_datetime.isoformat()
    mock_celery_task_result = MagicMock(id="celery-task-schedule-success")

    with patch('app.services.instant_nudge_service.process_scheduled_message_task.apply_async', return_value=mock_celery_task_result) as mock_apply_async, \
         patch('app.services.instant_nudge_service.datetime') as mock_datetime_service, \
         patch('app.services.instant_nudge_service.pytz.UTC.localize') as mock_pytz_localize:
        mock_datetime_service.now.return_value = now_utc
        naive_future_dt = datetime.fromisoformat(send_datetime_iso_str.replace('Z', '').split('+')[0])
        mock_datetime_service.fromisoformat.return_value = naive_future_dt
        mock_pytz_localize.return_value = future_datetime
        result = await handle_instant_nudge_batch(
            db, mock_business.id, customer_ids, message_content_template, send_datetime_iso=send_datetime_iso_str
        )
    assert result["scheduled_count"] == 1 and result["sent_count"] == 0
    mock_apply_async.assert_called_once()
    call_kwargs = mock_apply_async.call_args.kwargs
    assert call_kwargs['args'][0] == result["processed_message_ids"][0]
    assert call_kwargs['eta'] == future_datetime
    message = db.query(Message).get(result["processed_message_ids"][0])
    assert message is not None and message.status == MessageStatusEnum.SCHEDULED.value

@pytest.mark.asyncio
async def test_handle_instant_nudge_batch_schedule_past_datetime_sends_immediately(
    db: Session, mock_business: BusinessProfile, customer1: Customer
):
    message_content_template = "Past schedule, send now!"
    customer_ids = [customer1.id]
    now_utc = datetime.now(pytz.utc)
    past_datetime_iso_str = (now_utc - timedelta(hours=1)).isoformat()
    mock_twilio_service_instance = MagicMock(spec=TwilioService)
    mock_twilio_service_instance.send_sms = AsyncMock(return_value="SMmockpastschedule")

    with patch('app.services.instant_nudge_service.TwilioService', return_value=mock_twilio_service_instance) as MockTwilioService, \
         patch('app.services.instant_nudge_service.datetime') as mock_datetime_service, \
         patch('app.services.instant_nudge_service.process_scheduled_message_task.apply_async') as mock_apply_async:
        mock_datetime_service.now.return_value = now_utc
        mock_datetime_service.fromisoformat.return_value = datetime.fromisoformat(past_datetime_iso_str.replace('Z', '+00:00'))
        result = await handle_instant_nudge_batch(
            db, mock_business.id, customer_ids, message_content_template, send_datetime_iso=past_datetime_iso_str
        )
    assert result["sent_count"] == 1 and result["scheduled_count"] == 0
    mock_apply_async.assert_not_called()
    mock_twilio_service_instance.send_sms.assert_called_once()
    message = db.query(Message).get(result["processed_message_ids"][0])
    assert message.status == MessageStatusEnum.SENT.value

@pytest.mark.asyncio
async def test_handle_instant_nudge_batch_schedule_invalid_iso_sends_immediately(
    db: Session, mock_business: BusinessProfile, customer1: Customer
):
    message_content_template = "Invalid schedule, send now!"
    customer_ids = [customer1.id]
    invalid_iso_str = "not-a-valid-iso-date"
    mock_twilio_service_instance = MagicMock(spec=TwilioService)
    mock_twilio_service_instance.send_sms = AsyncMock(return_value="SMmockinvalidschedule")

    with patch('app.services.instant_nudge_service.TwilioService', return_value=mock_twilio_service_instance) as MockTwilioService, \
         patch('app.services.instant_nudge_service.datetime') as mock_datetime_service, \
         patch('app.services.instant_nudge_service.process_scheduled_message_task.apply_async') as mock_apply_async:
        mock_datetime_service.now.return_value = datetime.now(pytz.utc)
        mock_datetime_service.fromisoformat.side_effect = ValueError("Invalid ISO format")
        result = await handle_instant_nudge_batch(
            db, mock_business.id, customer_ids, message_content_template, send_datetime_iso=invalid_iso_str
        )
    assert result["sent_count"] == 1 and result["scheduled_count"] == 0
    mock_apply_async.assert_not_called()
    mock_twilio_service_instance.send_sms.assert_called_once()

@pytest.mark.asyncio
async def test_handle_instant_nudge_batch_empty_customer_ids(
    db: Session, mock_business: BusinessProfile
):
    result = await handle_instant_nudge_batch(db, mock_business.id, [], "No one to send to.")
    assert result["processed_message_ids"] == [] and result["sent_count"] == 0

@pytest.mark.asyncio
async def test_handle_instant_nudge_batch_business_not_found(db: Session, customer1: Customer):
    with pytest.raises(ValueError, match="Business not found for ID: 9999"):
        await handle_instant_nudge_batch(db, 9999, [customer1.id], "Business missing.")

@pytest.mark.asyncio
async def test_handle_instant_nudge_batch_some_customers_invalid_or_opted_out(
    db: Session, mock_business: BusinessProfile, customer1: Customer, customer2: Customer
):
    customer2.opted_in = False; db.add(customer2); db.commit()
    customer_ids = [customer1.id, customer2.id, 999] # 999 is non-existent
    mock_twilio_service_instance = MagicMock(spec=TwilioService)
    mock_twilio_service_instance.send_sms = AsyncMock(return_value="SMmockpartial")

    with patch('app.services.instant_nudge_service.TwilioService', return_value=mock_twilio_service_instance) as MockTwilioService, \
         patch('app.services.instant_nudge_service.datetime') as mock_datetime_service:
        mock_datetime_service.now.return_value = datetime.now(pytz.utc)
        result = await handle_instant_nudge_batch(
            db, mock_business.id, customer_ids, "Nudge for valid and invalid!", send_datetime_iso=None
        )
    assert result["sent_count"] == 1 and result["failed_count"] == 2
    assert len(result["processed_message_ids"]) == 1
    mock_twilio_service_instance.send_sms.assert_called_once()
    args_c1, kwargs_c1 = mock_twilio_service_instance.send_sms.call_args
    assert kwargs_c1['to'] == customer1.phone
    messages = db.query(Message).filter(Message.business_id == mock_business.id).all()
    assert len(messages) == 1 and messages[0].customer_id == customer1.id and messages[0].status == MessageStatusEnum.SENT.value

@pytest.mark.asyncio
async def test_handle_instant_nudge_batch_twilio_send_fails_for_one_customer(
    db: Session, mock_business: BusinessProfile, customer1: Customer, customer2: Customer
):
    customer_ids = [customer1.id, customer2.id]
    mock_twilio_service_instance = MagicMock(spec=TwilioService)
    async def send_sms_side_effect(to: str, message_body: str, business: Any, customer: Any, is_direct_reply: bool):
        if to == customer1.phone: raise HTTPException(status_code=500, detail="Twilio fake error")
        return "SMmock_success_c2"
    mock_twilio_service_instance.send_sms = AsyncMock(side_effect=send_sms_side_effect)

    with patch('app.services.instant_nudge_service.TwilioService', return_value=mock_twilio_service_instance) as MockTwilioService, \
         patch('app.services.instant_nudge_service.datetime') as mock_datetime_service:
        mock_datetime_service.now.return_value = datetime.now(pytz.utc)
        result = await handle_instant_nudge_batch(
            db, mock_business.id, customer_ids, "Trying to send to two, one will fail.", send_datetime_iso=None
        )
    assert result["sent_count"] == 1 and result["failed_count"] == 1
    assert len(result["processed_message_ids"]) == 1 # Only customer2's message ID
    msg_c1 = db.query(Message).filter(Message.customer_id == customer1.id).first()
    msg_c2 = db.query(Message).filter(Message.customer_id == customer2.id).first()

    assert msg_c1 is None # Because its transaction should have been rolled back
    assert msg_c2 is not None and msg_c2.status == MessageStatusEnum.SENT.value

@pytest.mark.asyncio
async def test_handle_instant_nudge_batch_celery_schedule_fails_for_one_customer(
    db: Session, mock_business: BusinessProfile, customer1: Customer, customer2: Customer
):
    customer_ids = [customer1.id, customer2.id]
    now_utc = datetime.now(pytz.utc)
    future_datetime = now_utc + timedelta(hours=2)
    send_datetime_iso_str = future_datetime.isoformat()
    apply_async_mock = MagicMock()
    def side_effect_based_on_call_count(*args, **kwargs):
        # This side effect needs to be robust to the actual message ID generated.
        # We assume customer1 (ID 101) is processed first.
        # The message ID is generated by DB sequence, so it might be > 1 if other tests ran.
        # A more robust mock might inspect args[0] (the message ID) and map it back to customer ID if needed.
        # For this test, just failing on the first call is sufficient.
        if apply_async_mock.call_count == 1:
            raise Exception("Celery down for first customer")
        mock_res = MagicMock(id="celery-task-c2-success")
        return mock_res
    apply_async_mock.side_effect = side_effect_based_on_call_count

    with patch('app.services.instant_nudge_service.process_scheduled_message_task.apply_async', apply_async_mock) as mock_apply_async_patched, \
         patch('app.services.instant_nudge_service.datetime') as mock_datetime_service:
        mock_datetime_service.now.return_value = now_utc
        mock_datetime_service.fromisoformat.return_value = datetime.fromisoformat(send_datetime_iso_str.replace('Z', '+00:00'))
        result = await handle_instant_nudge_batch(
            db, mock_business.id, customer_ids, "Scheduling two, one celery will fail.", send_datetime_iso=send_datetime_iso_str
        )
    assert result["scheduled_count"] == 1 and result["failed_count"] == 1
    assert len(result["processed_message_ids"]) == 1
    msg_c1_final = db.query(Message).filter(Message.customer_id == customer1.id).first()
    assert msg_c1_final is None # Rolled back
    msg_c2_final = db.query(Message).filter(Message.customer_id == customer2.id).first()
    assert msg_c2_final is not None and msg_c2_final.status == MessageStatusEnum.SCHEDULED.value
    # Service does not currently add celery_task_id to message_metadata for handle_instant_nudge_batch scheduling
    # If it did: assert msg_c2_final.message_metadata['celery_task_id'] == "celery-task-c2-success"
