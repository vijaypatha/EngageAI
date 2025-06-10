import pytest
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone as dt_timezone # Renamed to avoid conflict
from typing import List, Dict, Any
from unittest.mock import patch, MagicMock, AsyncMock # AsyncMock might not be needed if service method isn't async itself, but good to have
import uuid
from fastapi import HTTPException, status # Added for new tests
import pytz # For timezone handling

from app.models import (
    CoPilotNudge,
    Customer,
    BusinessProfile,
    Message,
    Conversation,
    NudgeStatusEnum,
    NudgeTypeEnum,
    MessageTypeEnum,
    MessageStatusEnum
)
from app.services.follow_up_plan_service import FollowUpPlanService
from app.schemas import ActivateEngagementPlanPayload, PlanMessage # MessageData for payload
from app.celery_app import celery_app # For mocking revoke

# Assuming conftest.py provides:
# - db: Session fixture
# - mock_business: BusinessProfile ORM instance fixture
# - mock_customer: Customer ORM instance fixture (will be used as customer1 for convenience)

@pytest.fixture
def customer1(mock_customer: Customer): # Use the conftest mock_customer as customer1
    return mock_customer

@pytest.fixture
def customer2(db: Session, mock_business: BusinessProfile):
    cust = Customer(business_id=mock_business.id, customer_name="Customer Two Test", phone="+15550000002", opted_in=True)
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return cust

@pytest.fixture
def follow_up_service(db: Session):
    return FollowUpPlanService(db=db)

# Helper to create a CoPilotNudge for follow-up plans
def create_follow_up_nudge(db: Session, business_id: int, customer_id: int,
                           status: NudgeStatusEnum = NudgeStatusEnum.ACTIVE,
                           payload: Dict[str, Any] = None):
    if payload is None:
        payload = {"plan_objective": "Test Follow-up"}
    nudge = CoPilotNudge(
        business_id=business_id,
        customer_id=customer_id,
        nudge_type=NudgeTypeEnum.STRATEGIC_ENGAGEMENT_OPPORTUNITY,
        status=status,
        message_snippet="Follow up with this customer.",
        ai_suggestion="Activate this plan.",
        ai_suggestion_payload=payload,
        created_at=datetime.now(dt_timezone.utc) - timedelta(days=1),
        updated_at=datetime.now(dt_timezone.utc) - timedelta(days=1)
    )
    db.add(nudge)
    db.commit()
    db.refresh(nudge)
    return nudge

@pytest.mark.asyncio
async def test_activate_plan_success_new_conversation(
    follow_up_service: FollowUpPlanService,
    db: Session,
    mock_business: BusinessProfile,
    mock_customer: Customer
):
    # Arrange
    now_utc = datetime.now(pytz.utc)
    message_data_list = [
        PlanMessage(text="Follow up message 1", send_datetime_utc=now_utc + timedelta(days=1)),
        PlanMessage(text="Follow up message 2", send_datetime_utc=now_utc + timedelta(days=3))
    ]
    payload = ActivateEngagementPlanPayload(customer_id=mock_customer.id, messages=message_data_list)

    nudge = create_follow_up_nudge(db, mock_business.id, mock_customer.id)

    mock_celery_task_result = MagicMock()
    mock_celery_task_result.id = "test-celery-task-id-" + str(uuid.uuid4())

    with patch('app.services.follow_up_plan_service.process_scheduled_message_task.apply_async', return_value=mock_celery_task_result) as mock_apply_async:
        # Act
        result = await follow_up_service.activate_plan_from_nudge(nudge.id, payload, mock_business.id)

    # Assert
    assert result["status"] == "success"
    assert result["created_message_ids"] is not None
    assert len(result["created_message_ids"]) == 2
    assert len(result["celery_task_ids"]) == 2

    db.refresh(nudge)
    assert nudge.status == NudgeStatusEnum.ACTIONED

    # Check conversation
    conversation = db.query(Conversation).filter(
        Conversation.customer_id == mock_customer.id,
        Conversation.business_id == mock_business.id
    ).first()
    assert conversation is not None
    assert conversation.status == 'active'

    # Check messages
    messages = db.query(Message).filter(Message.conversation_id == conversation.id).order_by(Message.scheduled_time).all()
    assert len(messages) == 2

    assert messages[0].content == "Follow up message 1"
    assert messages[0].status == MessageStatusEnum.SCHEDULED.value
    assert messages[0].message_metadata['celery_task_id'] is not None
    assert messages[0].message_metadata['source'] == 'follow_up_nudge_plan'

    assert messages[1].content == "Follow up message 2"
    assert messages[1].status == MessageStatusEnum.SCHEDULED.value

    assert mock_apply_async.call_count == 2
    # Check ETA for the first call (example)
    first_call_args = mock_apply_async.call_args_list[0]
    assert first_call_args.kwargs['args'][0] == result["created_message_ids"][0] # message.id
    # Ensure ETA is timezone-aware if scheduled_time is
    expected_eta1 = message_data_list[0].send_datetime_utc
    if expected_eta1.tzinfo is None: # if naive from schema
        expected_eta1 = pytz.utc.localize(expected_eta1)
    assert first_call_args.kwargs['eta'] == expected_eta1


@pytest.mark.asyncio
async def test_activate_plan_success_existing_conversation(
    follow_up_service: FollowUpPlanService, db: Session, mock_business: BusinessProfile, mock_customer: Customer
):
    # Arrange
    now_utc = datetime.now(pytz.utc)
    # Create existing conversation
    existing_convo = Conversation(
        customer_id=mock_customer.id,
        business_id=mock_business.id,
        status='active',
        started_at=now_utc - timedelta(days=5),
        last_message_at=now_utc - timedelta(days=5)
    )
    db.add(existing_convo)
    db.commit()
    db.refresh(existing_convo)

    message_data_list = [
        PlanMessage(text="Follow up message 3", send_datetime_utc=now_utc + timedelta(days=2))
    ]
    payload = ActivateEngagementPlanPayload(customer_id=mock_customer.id, messages=message_data_list)
    nudge = create_follow_up_nudge(db, mock_business.id, mock_customer.id)

    mock_celery_task_result = MagicMock()
    mock_celery_task_result.id = "celery-task-existing-convo"

    with patch('app.services.follow_up_plan_service.process_scheduled_message_task.apply_async', return_value=mock_celery_task_result) as mock_apply_async:
        # Act
        result = await follow_up_service.activate_plan_from_nudge(nudge.id, payload, mock_business.id)

    # Assert
    assert result["status"] == "success"
    assert len(result["created_message_ids"]) == 1

    db.refresh(nudge)
    assert nudge.status == NudgeStatusEnum.ACTIONED

    messages = db.query(Message).filter(Message.customer_id == mock_customer.id).all()
    assert len(messages) == 1 # Assuming no other messages for this customer in this test setup
    assert messages[0].conversation_id == existing_convo.id # Verify existing convo was used
    assert messages[0].content == "Follow up message 3"
    mock_apply_async.assert_called_once()

@pytest.mark.asyncio
async def test_activate_plan_nudge_not_found(follow_up_service: FollowUpPlanService, mock_business: BusinessProfile, mock_customer: Customer):
    dummy_message = PlanMessage(text="Test", send_datetime_utc=datetime.now(pytz.utc) + timedelta(hours=1))
    payload = ActivateEngagementPlanPayload(customer_id=mock_customer.id, messages=[dummy_message])
    with pytest.raises(HTTPException) as exc_info:
        await follow_up_service.activate_plan_from_nudge(9999, payload, mock_business.id)
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert "Nudge not found" in exc_info.value.detail

@pytest.mark.asyncio
async def test_activate_plan_nudge_wrong_type(follow_up_service: FollowUpPlanService, db: Session, mock_business: BusinessProfile, mock_customer: Customer):
    nudge = create_follow_up_nudge(db, mock_business.id, mock_customer.id) # Creates correct type initially
    nudge.nudge_type = NudgeTypeEnum.SENTIMENT_POSITIVE # Change to wrong type
    db.commit()
    dummy_message = PlanMessage(text="Test", send_datetime_utc=datetime.now(pytz.utc) + timedelta(hours=1))
    payload = ActivateEngagementPlanPayload(customer_id=mock_customer.id, messages=[dummy_message])
    with pytest.raises(HTTPException) as exc_info:
        await follow_up_service.activate_plan_from_nudge(nudge.id, payload, mock_business.id)
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "This action is only valid for STRATEGIC_ENGAGEMENT_OPPORTUNITY nudges" in exc_info.value.detail

@pytest.mark.asyncio
async def test_activate_plan_nudge_not_active(follow_up_service: FollowUpPlanService, db: Session, mock_business: BusinessProfile, mock_customer: Customer):
    nudge = create_follow_up_nudge(db, mock_business.id, mock_customer.id, status=NudgeStatusEnum.ACTIONED)
    dummy_message = PlanMessage(text="Test", send_datetime_utc=datetime.now(pytz.utc) + timedelta(hours=1))
    payload = ActivateEngagementPlanPayload(customer_id=mock_customer.id, messages=[dummy_message])
    with pytest.raises(HTTPException) as exc_info:
        await follow_up_service.activate_plan_from_nudge(nudge.id, payload, mock_business.id)
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Nudge is not active" in exc_info.value.detail

@pytest.mark.asyncio
async def test_activate_plan_customer_id_mismatch(
    follow_up_service: FollowUpPlanService, db: Session, mock_business: BusinessProfile, customer1: Customer, customer2: Customer
):
    nudge = create_follow_up_nudge(db, mock_business.id, customer1.id) # Nudge for customer1
    # Ensure customer fixtures are distinct if not already guaranteed by scope/setup
    payload = ActivateEngagementPlanPayload(customer_id=customer2.id, messages=[PlanMessage(text="Hi", send_datetime_utc=datetime.now(pytz.utc) + timedelta(days=1))]) # Payload for customer2
    with pytest.raises(HTTPException) as exc_info:
        await follow_up_service.activate_plan_from_nudge(nudge.id, payload, mock_business.id)
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Customer ID mismatch" in exc_info.value.detail

@pytest.mark.asyncio
async def test_activate_plan_some_messages_past_dated(
    follow_up_service: FollowUpPlanService, db: Session, mock_business: BusinessProfile, mock_customer: Customer
):
    now_utc = datetime.now(pytz.utc)
    message_data_list = [
        PlanMessage(text="Past message", send_datetime_utc=now_utc - timedelta(days=1)),
        PlanMessage(text="Future message", send_datetime_utc=now_utc + timedelta(days=1))
    ]
    payload = ActivateEngagementPlanPayload(customer_id=mock_customer.id, messages=message_data_list)
    nudge = create_follow_up_nudge(db, mock_business.id, mock_customer.id)

    mock_celery_task_result = MagicMock()
    mock_celery_task_result.id = "celery-task-past-dated"

    with patch('app.services.follow_up_plan_service.process_scheduled_message_task.apply_async', return_value=mock_celery_task_result) as mock_apply_async:
        result = await follow_up_service.activate_plan_from_nudge(nudge.id, payload, mock_business.id)

    assert result["status"] == "success"
    assert len(result["created_message_ids"]) == 1 # Only future message

    messages = db.query(Message).filter(Message.customer_id == mock_customer.id).all()
    assert len(messages) == 1
    assert messages[0].content == "Future message"
    mock_apply_async.assert_called_once() # Called only for the future message

@pytest.mark.asyncio
async def test_activate_plan_celery_apply_async_fails(
    follow_up_service: FollowUpPlanService, db: Session, mock_business: BusinessProfile, mock_customer: Customer
):
    now_utc = datetime.now(pytz.utc)
    message_data_list = [PlanMessage(text="Test message", send_datetime_utc=now_utc + timedelta(days=1))]
    payload = ActivateEngagementPlanPayload(customer_id=mock_customer.id, messages=message_data_list)
    nudge = create_follow_up_nudge(db, mock_business.id, mock_customer.id)

    with patch('app.services.follow_up_plan_service.process_scheduled_message_task.apply_async', side_effect=Exception("Celery down")) as mock_apply_async:
        with pytest.raises(HTTPException) as exc_info:
            await follow_up_service.activate_plan_from_nudge(nudge.id, payload, mock_business.id)

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to schedule messages" in exc_info.value.detail

    db.refresh(nudge) # Nudge status should not change
    assert nudge.status == NudgeStatusEnum.ACTIVE

    messages_count = db.query(Message).filter(Message.customer_id == mock_customer.id).count()
    assert messages_count == 0 # No messages should be committed

@pytest.mark.asyncio
async def test_activate_plan_final_commit_fails(
    follow_up_service: FollowUpPlanService, db: Session, mock_business: BusinessProfile, mock_customer: Customer
):
    now_utc = datetime.now(pytz.utc)
    message_data_list = [PlanMessage(text="Another message", send_datetime_utc=now_utc + timedelta(days=1))]
    payload = ActivateEngagementPlanPayload(customer_id=mock_customer.id, messages=message_data_list)
    nudge = create_follow_up_nudge(db, mock_business.id, mock_customer.id)

    mock_celery_task_result = MagicMock()
    mock_celery_task_result.id = "celery-task-commit-fail"

    with patch('app.services.follow_up_plan_service.process_scheduled_message_task.apply_async', return_value=mock_celery_task_result) as mock_apply_async, \
         patch.object(db, 'commit', side_effect=Exception("Final commit failed")) as mock_db_commit, \
         patch('app.services.follow_up_plan_service.celery_app.control.revoke') as mock_celery_revoke:

        with pytest.raises(HTTPException) as exc_info:
            await follow_up_service.activate_plan_from_nudge(nudge.id, payload, mock_business.id)

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to finalize plan activation" in exc_info.value.detail

    # Check that commit was attempted (after flush, before final exception)
    # The service has multiple db.commit() points; the one after celery tasks is the target.
    # For simplicity, we check it was called at least once before the mocked failure.
    # The critical one is the *last* commit. Here, we mock the final one.
    assert mock_db_commit.call_count > 0 # It's called after adding messages and before updating nudge

    mock_celery_revoke.assert_called_once_with("celery-task-commit-fail", terminate=True)

    db.rollback() # Clean up session from failed commit attempt in test
    db.refresh(nudge)
    assert nudge.status == NudgeStatusEnum.ACTIVE # Status should not have changed
