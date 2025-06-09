import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy.orm import Session
from fastapi import HTTPException
from fastapi.responses import PlainTextResponse

from app.services.consent_service import ConsentService
from app.models import (
    Customer,
    BusinessProfile,
    ConsentLog,
    Message,
    Conversation,
    OptInStatus,
    MessageTypeEnum,
    MessageStatusEnum
)
# TwilioService is imported within the patch path string, e.g., 'app.services.consent_service.TwilioService.send_sms'
# from app.services.twilio_service import TwilioService # Not strictly needed if only mocking methods

# Helper Fixtures
@pytest.fixture
def consent_service_instance(db: Session):
    return ConsentService(db=db) # Corrected parameter name

# Local test_business and test_customer fixtures removed, will use mock_business and mock_customer from conftest.py

# Test Cases

@pytest.mark.asyncio
async def test_send_double_optin_sms_customer_not_found(consent_service_instance: ConsentService, mock_business: BusinessProfile): # Changed to mock_business
    # Arrange
    non_existent_customer_id = 99999

    # Act
    result = await consent_service_instance.send_double_optin_sms(
        customer_id=non_existent_customer_id,
        business_id=test_business.id
    )

    # Assert
    assert result == {"success": False, "message": "Customer not found"}

@pytest.mark.asyncio
async def test_send_double_optin_sms_business_not_found(consent_service_instance: ConsentService, mock_customer: Customer): # Changed to mock_customer
    # Arrange
    non_existent_business_id = 99998

    # Act
    result = await consent_service_instance.send_double_optin_sms(
        customer_id=test_customer.id,
        business_id=non_existent_business_id
    )

    # Assert
    assert result == {"success": False, "message": "Business not found"}

@pytest.mark.asyncio
async def test_send_double_optin_sms_success_new_conversation(
    db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer # Changed
):
    # Arrange
    mock_twilio_sid = "SMxxxxxxxxxxxxxx"

    with patch('app.services.consent_service.TwilioService.send_sms', new_callable=AsyncMock) as mock_send_sms:
        mock_send_sms.return_value = mock_twilio_sid

        # Act
        result = await consent_service_instance.send_double_optin_sms(
            customer_id=test_customer.id,
            business_id=test_business.id
        )

    # Assert
    assert result["success"] is True
    assert result["message_sid"] == mock_twilio_sid

    mock_send_sms.assert_called_once()
    call_args = mock_send_sms.call_args[0]
    assert call_args[1] == test_customer.phone # 'to' number
    assert test_business.business_name in call_args[2] # 'body' contains business name
    assert "YES to consent" in call_args[2] # 'body' contains instruction

    # Check Conversation
    conversation = db.query(Conversation).filter(
        Conversation.customer_id == test_customer.id,
        Conversation.business_id == test_business.id
    ).first()
    assert conversation is not None
    assert result["conversation_id"] == str(conversation.id)


    # Check Message
    message = db.query(Message).filter(Message.conversation_id == conversation.id).first()
    assert message is not None
    assert message.content in call_args[2] # Message content matches what was sent
    assert message.message_type == MessageTypeEnum.OUTBOUND.value
    assert message.status == MessageStatusEnum.SENT.value # Assuming Twilio success implies sent

    # Check ConsentLog
    consent_log = db.query(ConsentLog).filter(
        ConsentLog.customer_id == test_customer.id,
        ConsentLog.business_id == test_business.id
    ).first()
    assert consent_log is not None
    assert consent_log.status == "pending_confirmation"
    assert consent_log.message_sid == mock_twilio_sid

@pytest.mark.asyncio
async def test_send_double_optin_sms_success_existing_conversation(
    db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer # Changed
):
    # Arrange
    # Create existing conversation
    existing_conversation = Conversation(
        customer_id=test_customer.id,
        business_id=test_business.id,
    )
    db.add(existing_conversation)
    db.commit()
    db.refresh(existing_conversation)
    initial_last_message_at = existing_conversation.last_message_at

    mock_twilio_sid = "SMyyyyyyyyyyyyyy"

    with patch('app.services.consent_service.TwilioService.send_sms', new_callable=AsyncMock) as mock_send_sms:
        mock_send_sms.return_value = mock_twilio_sid

        # Act
        result = await consent_service_instance.send_double_optin_sms(
            customer_id=test_customer.id,
            business_id=test_business.id
        )

    # Assert
    assert result["success"] is True
    assert result["message_sid"] == mock_twilio_sid
    assert result["conversation_id"] == str(existing_conversation.id) # Should use existing

    mock_send_sms.assert_called_once()

    db.refresh(existing_conversation)
    assert existing_conversation.last_message_at is not None
    assert existing_conversation.last_message_at > initial_last_message_at

    # Check Message (new message in existing conversation)
    # Similar to the new conversation test, check for the message content and status
    call_args_body = mock_send_sms.call_args[0][2] # Get the body text sent to Twilio
    message = db.query(Message).filter(
        Message.conversation_id == existing_conversation.id,
        Message.content == call_args_body, # Exact match for sent content
        Message.message_type == MessageTypeEnum.OUTBOUND.value
    ).order_by(Message.created_at.desc()).first()

    assert message is not None
    assert message.status == MessageStatusEnum.SENT.value # Assuming Twilio success implies sent

    # Check ConsentLog
    consent_log = db.query(ConsentLog).filter(ConsentLog.message_sid == mock_twilio_sid).first()
    assert consent_log is not None
    assert consent_log.status == "pending_confirmation"

@pytest.mark.asyncio
async def test_send_double_optin_sms_twilio_failure(
    db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer # Changed
):
    # Arrange
    with patch('app.services.consent_service.TwilioService.send_sms', new_callable=AsyncMock) as mock_send_sms:
        mock_send_sms.return_value = None # Simulate Twilio failure

        # Act
        result = await consent_service_instance.send_double_optin_sms(
            customer_id=test_customer.id,
            business_id=test_business.id
        )

    # Assert
    assert result["success"] is False
    assert result["message"] == "Failed to send opt-in SMS via provider."
    mock_send_sms.assert_called_once()

    # Check Message status
    conversation = db.query(Conversation).filter(Conversation.customer_id == test_customer.id).first()
    assert conversation is not None # Conversation should still be created

    message = db.query(Message).filter(Message.conversation_id == conversation.id).first()
    assert message is not None
    assert message.status == MessageStatusEnum.FAILED.value # Status should be FAILED

    # Check ConsentLog (still created)
    consent_log = db.query(ConsentLog).filter(
        ConsentLog.customer_id == test_customer.id,
        ConsentLog.business_id == test_business.id
    ).first()
    assert consent_log is not None
    assert consent_log.status == "pending_confirmation" # Log is created, but message failed
    assert consent_log.message_sid is None


@pytest.mark.asyncio
async def test_process_sms_response_opt_in(
    db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer # Changed
):
    # Arrange
    # Create a pending consent log
    pending_log = ConsentLog(
        customer_id=test_customer.id,
        business_id=test_business.id,
        phone_number=test_customer.phone,
        status="pending_confirmation",
        method="sms_double_opt_in"
    )
    db.add(pending_log)
    db.commit()

    # Act
    response = await consent_service_instance.process_sms_response(
        from_phone=test_customer.phone,
        message_body="YES" # Opt-in keyword
    )

    # Assert
    assert isinstance(response, PlainTextResponse)
    assert response.status_code == 200
    assert "You have successfully opted in" in response.body.decode()

    db.refresh(test_customer)
    assert test_customer.sms_opt_in_status == OptInStatus.OPTED_IN.value
    assert test_customer.opted_in is True

    db.refresh(pending_log)
    assert pending_log.status == "opted_in"


@pytest.mark.asyncio
async def test_process_sms_response_opt_out_global(
    db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer # Changed
):
    # Arrange
    # Customer might be opted-in or pending
    test_customer.sms_opt_in_status = OptInStatus.OPTED_IN.value
    test_customer.opted_in = True
    db.commit()

    # Create a relevant consent log (could be opted_in or pending_confirmation)
    existing_log = ConsentLog(
        customer_id=test_customer.id,
        business_id=test_business.id,
        phone_number=test_customer.phone,
        status="opted_in", # or pending_confirmation
        method="sms_double_opt_in"
    )
    db.add(existing_log)
    db.commit()


    # Act
    response = await consent_service_instance.process_sms_response(
        from_phone=test_customer.phone,
        message_body="STOP" # Global opt-out keyword
    )

    # Assert
    assert isinstance(response, PlainTextResponse)
    assert response.status_code == 200
    assert "You have successfully opted out" in response.body.decode()


    db.refresh(test_customer)
    assert test_customer.sms_opt_in_status == OptInStatus.OPTED_OUT.value
    assert test_customer.opted_in is False

    db.refresh(existing_log)
    assert existing_log.status == "opted_out" # Log associated with this interaction is updated

@pytest.mark.asyncio
async def test_process_sms_response_no_pending_log(
    db: Session, consent_service_instance: ConsentService, mock_customer: Customer # Changed
):
    # Arrange
    # Ensure no 'pending_confirmation' log for this customer
    db.query(ConsentLog).filter(ConsentLog.phone_number == test_customer.phone).delete()
    db.commit()

    # Act
    response = await consent_service_instance.process_sms_response(
        from_phone=test_customer.phone,
        message_body="HELLO" # Some other message
    )

    # Assert
    assert response is None # Or specific response indicating no action taken if service handles it differently

@pytest.mark.asyncio
async def test_check_consent_true(consent_service_instance: ConsentService, mock_customer: Customer, db: Session): # Changed
    # Arrange
    test_customer.sms_opt_in_status = OptInStatus.OPTED_IN.value
    db.commit()
    db.refresh(test_customer)

    # Act
    result = await consent_service_instance.check_consent(customer_id=test_customer.id, business_id=test_customer.business_id)

    # Assert
    assert result is True

@pytest.mark.asyncio
async def test_check_consent_false(consent_service_instance: ConsentService, mock_customer: Customer, db: Session): # Changed
    # Arrange
    test_customer.sms_opt_in_status = OptInStatus.OPTED_OUT.value
    db.commit()
    db.refresh(test_customer)

    # Act
    result = await consent_service_instance.check_consent(customer_id=test_customer.id, business_id=test_customer.business_id)

    # Assert
    assert result is False

@pytest.mark.asyncio
async def test_get_consent_history(db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer): # Changed
    # Arrange
    log1 = ConsentLog(customer_id=test_customer.id, business_id=test_business.id, method="sms", status="pending_confirmation", phone_number=test_customer.phone)
    log2 = ConsentLog(customer_id=test_customer.id, business_id=test_business.id, method="sms", status="opted_in", phone_number=test_customer.phone)
    db.add_all([log1, log2])
    db.commit()

    # Act
    history = await consent_service_instance.get_consent_history(customer_id=test_customer.id, business_id=test_business.id)

    # Assert
    assert len(history) == 2
    history_methods = [h.method for h in history]
    history_statuses = [h.status for h in history]
    assert "sms" in history_methods
    assert "pending_confirmation" in history_statuses
    assert "opted_in" in history_statuses


@pytest.mark.asyncio
async def test_handle_opt_in_manual(db: Session, consent_service_instance: ConsentService, mock_customer: Customer): # Changed
    # Arrange
    # Customer starts as not opted-in
    test_customer.sms_opt_in_status = OptInStatus.NOT_SET.value
    test_customer.opted_in = False
    db.commit()
    db.refresh(test_customer)

    # Act
    consent_log = await consent_service_instance.handle_opt_in(
        customer_id=test_customer.id,
        business_id=test_customer.business_id,
        method_detail="Manual admin override"
    )

    # Assert
    assert consent_log is not None
    assert consent_log.method == "manual_override" # As per ConsentService logic for handle_opt_in
    assert consent_log.status == "opted_in"
    assert consent_log.customer_id == test_customer.id

    db.refresh(test_customer)
    assert test_customer.sms_opt_in_status == OptInStatus.OPTED_IN.value
    assert test_customer.opted_in is True

@pytest.mark.asyncio
async def test_handle_opt_out_manual(db: Session, consent_service_instance: ConsentService, mock_customer: Customer): # Changed
    # Arrange
    # Customer starts as opted-in
    test_customer.sms_opt_in_status = OptInStatus.OPTED_IN.value
    test_customer.opted_in = True
    db.commit()
    db.refresh(test_customer)

    # Act
    consent_log = await consent_service_instance.handle_opt_out(
        customer_id=test_customer.id,
        business_id=test_customer.business_id,
        method_detail="Manual admin override for opt-out"
    )

    # Assert
    assert consent_log is not None
    assert consent_log.method == "manual_override" # As per ConsentService logic for handle_opt_out
    assert consent_log.status == "opted_out"
    assert consent_log.customer_id == test_customer.id

    db.refresh(test_customer)
    assert test_customer.sms_opt_in_status == OptInStatus.OPTED_OUT.value
    assert test_customer.opted_in is False

# Add a final newline for PEP8
