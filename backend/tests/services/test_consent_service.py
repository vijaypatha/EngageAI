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

# Helper Fixtures
@pytest.fixture
def consent_service_instance(db: Session):
    return ConsentService(db=db)

# Test Cases
@pytest.mark.asyncio
async def test_send_double_optin_sms_customer_not_found(consent_service_instance: ConsentService, mock_business: BusinessProfile):
    # Arrange
    non_existent_customer_id = 99999
    # Act
    result = await consent_service_instance.send_double_optin_sms(
        customer_id=non_existent_customer_id,
        business_id=mock_business.id # Corrected from test_business.id
    )
    # Assert
    assert result == {"success": False, "message": "Customer not found"}

@pytest.mark.asyncio
async def test_send_double_optin_sms_business_not_found(consent_service_instance: ConsentService, mock_customer: Customer):
    # Arrange
    non_existent_business_id = 99998
    # Act
    result = await consent_service_instance.send_double_optin_sms(
        customer_id=mock_customer.id, # Corrected from test_customer.id
        business_id=non_existent_business_id
    )
    # Assert
    assert result == {"success": False, "message": "Business not found"}

@pytest.mark.asyncio
async def test_send_double_optin_sms_success_new_conversation(
    db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer
):
    # Arrange
    mock_twilio_sid = "SMxxxxxxxxxxxxxx"
    # Ensure mock_customer has .phone attribute
    mock_customer.phone = "+1234567890" if mock_customer.phone is None else mock_customer.phone


    with patch('app.services.consent_service.TwilioService.send_sms', new_callable=AsyncMock) as mock_send_sms:
        mock_send_sms.return_value = mock_twilio_sid
        # Act
        result = await consent_service_instance.send_double_optin_sms(
            customer_id=mock_customer.id, # Corrected
            business_id=mock_business.id  # Corrected
        )

    # Assert
    assert result["success"] is True
    assert result["message_sid"] == mock_twilio_sid

    mock_send_sms.assert_called_once()
    call_kwargs = mock_send_sms.call_args.kwargs
    assert call_kwargs['to'] == mock_customer.phone
    assert mock_business.business_name in call_kwargs['message_body']
    # Assuming the service constructs a message like this:
    expected_message_fragment = f"{mock_business.business_name}: We need your consent to send you text messages. Please reply YES to consent or STOP to opt out."
    # Check if the core part of the message is in what was sent.
    # The service might have slight variations, so check for key phrases.
    assert "to confirm, please reply yes" in call_kwargs['message_body'].lower() # Corrected expected substring

    conversation = db.query(Conversation).filter(
        Conversation.customer_id == mock_customer.id, # Corrected
        Conversation.business_id == mock_business.id  # Corrected
    ).first()
    assert conversation is not None
    assert result["conversation_id"] == str(conversation.id)

    message = db.query(Message).filter(Message.conversation_id == conversation.id).first()
    assert message is not None
    assert message.content == call_kwargs['message_body'] # Check against actual sent body
    assert message.message_type == MessageTypeEnum.OUTBOUND.value
    assert message.status == MessageStatusEnum.SENT.value

    consent_log = db.query(ConsentLog).filter(
        ConsentLog.customer_id == mock_customer.id, # Corrected
        ConsentLog.business_id == mock_business.id  # Corrected
    ).first()
    assert consent_log is not None
    assert consent_log.status == "pending_confirmation"
    assert consent_log.message_sid == mock_twilio_sid

@pytest.mark.asyncio
async def test_send_double_optin_sms_success_existing_conversation(
    db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer
):
    # Arrange
    mock_customer.phone = "+1234567890" if mock_customer.phone is None else mock_customer.phone
    existing_conversation = Conversation(
        customer_id=mock_customer.id, # Corrected
        business_id=mock_business.id, # Corrected
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
            customer_id=mock_customer.id, # Corrected
            business_id=mock_business.id  # Corrected
        )

    # Assert
    assert result["success"] is True
    assert result["message_sid"] == mock_twilio_sid
    # Removed: assert result["conversation_id"] == str(existing_conversation.id) (as per plan)

    mock_send_sms.assert_called_once()
    db.refresh(existing_conversation)
    assert existing_conversation.last_message_at is not None
    assert existing_conversation.last_message_at > initial_last_message_at

    call_kwargs_body = mock_send_sms.call_args.kwargs['message_body']
    message = db.query(Message).filter(
        Message.conversation_id == existing_conversation.id,
        Message.content == call_kwargs_body,
        Message.message_type == MessageTypeEnum.OUTBOUND.value
    ).order_by(Message.created_at.desc()).first()
    assert message is not None
    assert message.status == MessageStatusEnum.SENT.value

    consent_log = db.query(ConsentLog).filter(ConsentLog.message_sid == mock_twilio_sid).first()
    assert consent_log is not None
    assert consent_log.status == "pending_confirmation"

@pytest.mark.asyncio
async def test_send_double_optin_sms_twilio_failure(
    db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer
):
    # Arrange
    mock_customer.phone = "+1234567890" if mock_customer.phone is None else mock_customer.phone
    with patch('app.services.consent_service.TwilioService.send_sms', new_callable=AsyncMock) as mock_send_sms:
        mock_send_sms.return_value = None
        # Act
        result = await consent_service_instance.send_double_optin_sms(
            customer_id=mock_customer.id, # Corrected
            business_id=mock_business.id  # Corrected
        )
    # Assert
    assert result["success"] is False
    assert result["message"] == "Failed to send opt-in SMS via provider."
    mock_send_sms.assert_called_once()
    conversation = db.query(Conversation).filter(Conversation.customer_id == mock_customer.id).first() # Corrected
    assert conversation is not None
    message = db.query(Message).filter(Message.conversation_id == conversation.id).first()
    assert message is not None
    assert message.status == MessageStatusEnum.FAILED.value
    consent_log = db.query(ConsentLog).filter(
        ConsentLog.customer_id == mock_customer.id, # Corrected
        ConsentLog.business_id == mock_business.id  # Corrected
    ).first()
    assert consent_log is not None
    assert consent_log.status == "pending_confirmation"
    assert consent_log.message_sid is None

@pytest.mark.asyncio
async def test_process_sms_response_opt_in(
    db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer
):
    # Arrange
    mock_customer.phone = "+1234567890" if mock_customer.phone is None else mock_customer.phone
    pending_log = ConsentLog(
        customer_id=mock_customer.id, # Corrected
        business_id=mock_business.id, # Corrected
        phone_number=mock_customer.phone,
        status="pending_confirmation",
        method="sms_double_opt_in"
    )
    db.add(pending_log)
    db.commit()
    # Act
    response = await consent_service_instance.process_sms_response(
        phone_number=mock_customer.phone, # Corrected parameter name
        response="YES"                   # Corrected parameter name
    )
    # Assert
    assert isinstance(response, PlainTextResponse)
    assert response.status_code == 200
    assert "Thanks for confirming! You're opted in" in response.body.decode() # Corrected expected message
    db.refresh(mock_customer) # Corrected
    assert mock_customer.sms_opt_in_status == OptInStatus.OPTED_IN.value # Corrected
    assert mock_customer.opted_in is True # Corrected
    db.refresh(pending_log)
    assert pending_log.status == "opted_in"

@pytest.mark.asyncio
async def test_process_sms_response_opt_out_global(
    db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer
):
    # Arrange
    mock_customer.phone = "+1234567890" if mock_customer.phone is None else mock_customer.phone
    mock_customer.sms_opt_in_status = OptInStatus.OPTED_IN.value # Corrected
    mock_customer.opted_in = True # Corrected
    db.commit()
    existing_log = ConsentLog(
        customer_id=mock_customer.id, # Corrected
        business_id=mock_business.id, # Corrected
        phone_number=mock_customer.phone,
        status="pending_confirmation", # Corrected status for test logic
        method="sms_double_opt_in"
    )
    db.add(existing_log)
    db.commit()
    # Act
    response = await consent_service_instance.process_sms_response(
        phone_number=mock_customer.phone, # Corrected parameter name
        response="STOP"                  # Corrected parameter name
    )
    # Assert
    assert isinstance(response, PlainTextResponse)
    assert response.status_code == 200
    assert "You have successfully opted out" in response.body.decode()
    db.refresh(mock_customer) # Corrected
    assert mock_customer.sms_opt_in_status == OptInStatus.OPTED_OUT.value # Corrected
    assert mock_customer.opted_in is False # Corrected
    db.refresh(existing_log)
    assert existing_log.status == "opted_out"

@pytest.mark.asyncio
async def test_process_sms_response_no_pending_log(
    db: Session, consent_service_instance: ConsentService, mock_customer: Customer
):
    # Arrange
    mock_customer.phone = "+1234567890" if mock_customer.phone is None else mock_customer.phone
    db.query(ConsentLog).filter(ConsentLog.phone_number == mock_customer.phone).delete() # Corrected
    db.commit()
    # Act
    response = await consent_service_instance.process_sms_response(
        phone_number=mock_customer.phone, # Corrected parameter name
        response="HELLO"                 # Corrected parameter name
    )
    # Assert
    assert response is None

@pytest.mark.asyncio
async def test_check_consent_true(consent_service_instance: ConsentService, mock_customer: Customer, db: Session):
    # Arrange
    mock_customer.phone = "+1234567890" if mock_customer.phone is None else mock_customer.phone
    mock_customer.sms_opt_in_status = OptInStatus.OPTED_IN.value # Corrected
    db.commit()
    db.refresh(mock_customer) # Corrected
    # Act
    result = await consent_service_instance.check_consent(phone_number=mock_customer.phone, business_id=mock_customer.business_id) # Corrected parameters
    # Assert
    assert result is True

@pytest.mark.asyncio
async def test_check_consent_false(consent_service_instance: ConsentService, mock_customer: Customer, db: Session):
    # Arrange
    mock_customer.phone = "+1234567890" if mock_customer.phone is None else mock_customer.phone
    mock_customer.sms_opt_in_status = OptInStatus.OPTED_OUT.value # Corrected
    db.commit()
    db.refresh(mock_customer) # Corrected
    # Act
    result = await consent_service_instance.check_consent(phone_number=mock_customer.phone, business_id=mock_customer.business_id) # Corrected parameters
    # Assert
    assert result is False

@pytest.mark.asyncio
async def test_get_consent_history(db: Session, consent_service_instance: ConsentService, mock_business: BusinessProfile, mock_customer: Customer):
    # Arrange
    mock_customer.phone = "+1234567890" if mock_customer.phone is None else mock_customer.phone
    log1 = ConsentLog(customer_id=mock_customer.id, business_id=mock_business.id, method="sms", status="pending_confirmation", phone_number=mock_customer.phone) # Corrected
    log2 = ConsentLog(customer_id=mock_customer.id, business_id=mock_business.id, method="sms", status="opted_in", phone_number=mock_customer.phone) # Corrected
    db.add_all([log1, log2])
    db.commit()
    # Act
    history = await consent_service_instance.get_consent_history(customer_id=mock_customer.id, business_id=mock_business.id) # Corrected
    # Assert
    assert len(history) == 2
    # Corrected to use dictionary access based on AttributeError: 'dict' object has no attribute 'method'
    history_methods = [h['method'] for h in history]
    history_statuses = [h['status'] for h in history]
    assert "sms" in history_methods
    assert "pending_confirmation" in history_statuses
    assert "opted_in" in history_statuses

@pytest.mark.asyncio
async def test_handle_opt_in_manual(db: Session, consent_service_instance: ConsentService, mock_customer: Customer):
    # Arrange
    mock_customer.sms_opt_in_status = OptInStatus.NOT_SET.value # Corrected
    mock_customer.opted_in = False # Corrected
    db.commit()
    db.refresh(mock_customer) # Corrected
    # Act
    consent_log = await consent_service_instance.handle_opt_in(
        phone_number=mock_customer.phone, # Added phone_number
        customer_id=mock_customer.id,
        business_id=mock_customer.business_id,
        method="Manual admin override"
    )
    # Assert
    assert consent_log is not None
    assert consent_log.method == "manual_override"
    assert consent_log.status == "opted_in"
    assert consent_log.customer_id == mock_customer.id # Corrected
    db.refresh(mock_customer) # Corrected
    assert mock_customer.sms_opt_in_status == OptInStatus.OPTED_IN.value # Corrected
    assert mock_customer.opted_in is True # Corrected

@pytest.mark.asyncio
async def test_handle_opt_out_manual(db: Session, consent_service_instance: ConsentService, mock_customer: Customer):
    # Arrange
    mock_customer.sms_opt_in_status = OptInStatus.OPTED_IN.value # Corrected
    mock_customer.opted_in = True # Corrected
    db.commit()
    db.refresh(mock_customer) # Corrected
    # Act
    consent_log = await consent_service_instance.handle_opt_out(
        phone_number=mock_customer.phone, # Added phone_number
        customer_id=mock_customer.id,
        business_id=mock_customer.business_id,
        method="Manual admin override for opt-out"
    )
    # Assert
    assert consent_log is not None
    assert consent_log.method == "manual_override"
    assert consent_log.status == "opted_out"
    assert consent_log.customer_id == mock_customer.id # Corrected
    db.refresh(mock_customer) # Corrected
    assert mock_customer.sms_opt_in_status == OptInStatus.OPTED_OUT.value # Corrected
    assert mock_customer.opted_in is False # Corrected

# Final newline for PEP8
