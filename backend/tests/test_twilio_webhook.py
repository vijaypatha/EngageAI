import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch, ANY
from sqlalchemy.orm import Session
from fastapi import status, Request
from fastapi.responses import PlainTextResponse
from datetime import datetime
import pytz
import json

from app.models import BusinessProfile as BusinessProfileModel
from app.models import Customer as CustomerModel
from app.models import Conversation as ConversationModel
from app.models import Message as MessageModel
from app.models import Engagement as EngagementModel
from app.models import ConsentLog as ConsentLogModel
from app.models import OptInStatus, MessageStatusEnum, MessageTypeEnum
from app.database import get_db
from app.schemas import normalize_phone_number

# Import services to be mocked
from app.services.twilio_service import TwilioService
from app.services.ai_service import AIService
from app.services.consent_service import ConsentService


# Default form data for Twilio webhook
DEFAULT_FORM_DATA = {
    "MessageSid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "SmsSid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "AccountSid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "MessagingServiceSid": "MGxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "From": "+15551112222", # Customer
    "To": "+15557778888",   # Business Twilio Number
    "Body": "Hello there!",
    "NumMedia": "0"
}

@pytest.fixture
def mock_consent_service_instance(db: Session):
    mock = MagicMock(spec=ConsentService)
    mock.process_sms_response = AsyncMock(return_value=None)
    return mock

@pytest.fixture
def mock_ai_service_instance(db: Session):
    mock = MagicMock(spec=AIService)
    mock.generate_sms_response = AsyncMock(return_value={"text": "AI General Reply", "is_faq_answer": False, "ai_should_reply_directly_as_faq": False})
    return mock

@pytest.fixture
def mock_twilio_service_instance(db: Session):
    mock = MagicMock(spec=TwilioService)
    mock.send_sms = AsyncMock(return_value="SMmocktwiliosid")
    return mock

@pytest.fixture(autouse=True)
def setup_webhook_test_overrides(
    test_app_client_fixture: TestClient,
    mock_db_session: MagicMock,
    mock_consent_service_instance: MagicMock,
    mock_ai_service_instance: MagicMock,
    mock_twilio_service_instance: MagicMock
):
    app_instance = test_app_client_fixture.app
    app_instance.dependency_overrides[get_db] = lambda: mock_db_session

    patcher_consent = patch('app.routes.twilio_webhook.ConsentService', return_value=mock_consent_service_instance)
    patcher_ai = patch('app.routes.twilio_webhook.AIService', return_value=mock_ai_service_instance)
    patcher_twilio = patch('app.routes.twilio_webhook.TwilioService', return_value=mock_twilio_service_instance)

    started_patchers = [patcher_consent.start(), patcher_ai.start(), patcher_twilio.start()]

    yield

    for p in started_patchers:
        p.stop()
    app_instance.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_receive_sms_basic_success(
    test_app_client_fixture: TestClient,
    mock_db_session: MagicMock,
    mock_consent_service_instance: MagicMock,
    mock_ai_service_instance: MagicMock,
    mock_twilio_service_instance: MagicMock,
    mock_business: BusinessProfileModel,
    mock_customer: CustomerModel
):
    # Ensure mock_business and mock_customer have valid, normalizable phone numbers and consistent IDs
    # These mock_business and mock_customer come from conftest.py and should have IDs.
    # If not, they need to be set: e.g. mock_business.id = 1; mock_customer.id = 1;
    mock_business.twilio_number = DEFAULT_FORM_DATA["To"]
    mock_customer.phone = DEFAULT_FORM_DATA["From"]
    if mock_business.id is None: mock_business.id = 1 # Ensure ID is set
    mock_customer.business_id = mock_business.id
    if mock_customer.id is None: mock_customer.id = 1


    form_data = {**DEFAULT_FORM_DATA}

    mock_business.enable_ai_faq_auto_reply = False
    mock_business.notify_owner_on_reply_with_link = False

    normalized_to_phone = normalize_phone_number(form_data["To"])
    normalized_from_phone = normalize_phone_number(form_data["From"])

    # Specific query mocks
    # Mock for BusinessProfile query
    query_bp_mock = MagicMock()
    query_bp_mock.filter(BusinessProfileModel.twilio_number == normalized_to_phone).first.return_value = mock_business

    # Mock for Customer query
    query_cust_mock = MagicMock()
    query_cust_mock.filter(CustomerModel.phone == normalized_from_phone, CustomerModel.business_id == mock_business.id).first.return_value = mock_customer

    # Mock for Conversation query
    query_conv_mock = MagicMock()
    query_conv_mock.filter(
        ConversationModel.customer_id == mock_customer.id,
        ConversationModel.business_id == mock_business.id,
        ConversationModel.status == "active"
    ).first.return_value = None

    # Mock for ConsentLog query
    mock_latest_consent_log = MagicMock(spec=ConsentLogModel)
    mock_latest_consent_log.status = OptInStatus.OPTED_IN.value
    query_consent_mock = MagicMock()
    query_consent_mock.filter(
        ConsentLogModel.customer_id == mock_customer.id,
        ConsentLogModel.business_id == mock_business.id
    ).order_by(ConsentLogModel.created_at.desc()).first.return_value = mock_latest_consent_log

    def query_side_effect(model_class):
        if model_class == BusinessProfileModel:
            return query_bp_mock
        elif model_class == CustomerModel:
            return query_cust_mock
        elif model_class == ConversationModel:
            return query_conv_mock
        elif model_class == ConsentLogModel:
            return query_consent_mock
        return MagicMock()

    mock_db_session.query = MagicMock(side_effect=query_side_effect)

    response = test_app_client_fixture.post("/twilio/inbound", data=form_data)

    assert response.status_code == status.HTTP_200_OK
    assert "SMS Received and Processed" in response.text

    mock_db_session.add.assert_called()
    mock_db_session.commit.assert_called()

    mock_consent_service_instance.process_sms_response.assert_called_once()
    mock_ai_service_instance.generate_sms_response.assert_called_once()
    mock_twilio_service_instance.send_sms.assert_not_called()
