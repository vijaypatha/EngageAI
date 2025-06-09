# sys.path modifications removed
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock
from fastapi import HTTPException, status # Added status here
from datetime import datetime, timezone

# Imports adjusted for running pytest from backend/
from app.models import BusinessProfile, Customer, ConsentLog, OptInStatus
from app.schemas import ConsentResponse, ConsentCreate
from app.database import get_db
from app.auth import get_current_user
from app.services.consent_service import ConsentService
from app.routes.consent_routes import get_consent_service

@pytest.fixture
def mock_consent_service_for_routes():
    return MagicMock(spec=ConsentService)

@pytest.fixture(autouse=True)
def setup_api_test_overrides(
    mock_db_session: MagicMock,
    mock_current_user_fixture: BusinessProfile,
    mock_consent_service_for_routes: MagicMock
):
    from main import app as main_app_for_overrides

    main_app_for_overrides.dependency_overrides[get_db] = lambda: mock_db_session
    main_app_for_overrides.dependency_overrides[get_current_user] = lambda: mock_current_user_fixture
    main_app_for_overrides.dependency_overrides[get_consent_service] = lambda: mock_consent_service_for_routes

    yield

    main_app_for_overrides.dependency_overrides.clear()

# Test Cases

def test_opt_in_success(test_app_client_fixture: TestClient, mock_consent_service_for_routes: MagicMock, mock_current_user_fixture: BusinessProfile):
    # Arrange
    consent_data = {"phone_number": "+11234567890", "business_id": mock_current_user_fixture.id, "customer_id": 1, "method": "api_test"}
    mock_consent_log = MagicMock(spec=ConsentLog)
    mock_consent_log.id = 1
    mock_consent_log.customer_id = consent_data["customer_id"]
    mock_consent_log.business_id = consent_data["business_id"]
    mock_consent_log.phone_number = consent_data["phone_number"]
    mock_consent_log.status = OptInStatus.OPTED_IN.value
    mock_consent_log.method = consent_data["method"]
    mock_consent_log.message_sid = "SMmockmessageidoptin"
    mock_consent_log.created_at = datetime.now(timezone.utc)
    mock_consent_log.updated_at = datetime.now(timezone.utc)
    mock_consent_log.sent_at = datetime.now(timezone.utc)
    mock_consent_log.replied_at = datetime.now(timezone.utc)

    mock_consent_service_for_routes.handle_opt_in = AsyncMock(return_value=mock_consent_log)

    # Act
    response = test_app_client_fixture.post("/consent/opt-in", json=consent_data)

    # Assert
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["customer_id"] == consent_data["customer_id"]
    assert json_response["status"] == OptInStatus.OPTED_IN.value
    mock_consent_service_for_routes.handle_opt_in.assert_called_once_with(
        phone_number=consent_data["phone_number"],
        customer_id=consent_data["customer_id"],
        business_id=consent_data["business_id"]
    )

def test_opt_in_service_error(test_app_client_fixture: TestClient, mock_consent_service_for_routes: MagicMock, mock_current_user_fixture: BusinessProfile):
    # Arrange
    consent_data = {"phone_number": "+11234567890", "business_id": mock_current_user_fixture.id, "customer_id": 1, "method": "api_test"}

    mock_consent_service_for_routes.handle_opt_in = AsyncMock(side_effect=HTTPException(status_code=500, detail="Service Error"))

    # Act
    response = test_app_client_fixture.post("/consent/opt-in", json=consent_data)

    # Assert
    assert response.status_code == 500
    assert response.json() == {"detail": "500: Service Error"}

def test_opt_out_success(test_app_client_fixture: TestClient, mock_consent_service_for_routes: MagicMock, mock_current_user_fixture: BusinessProfile):
    # Arrange
    consent_data = {"phone_number": "+11234567890", "business_id": mock_current_user_fixture.id, "customer_id": 1, "method": "api_test"}
    mock_consent_log = MagicMock(spec=ConsentLog)
    mock_consent_log.id = 2
    mock_consent_log.customer_id = consent_data["customer_id"]
    mock_consent_log.business_id = consent_data["business_id"]
    mock_consent_log.phone_number = consent_data["phone_number"]
    mock_consent_log.status = OptInStatus.OPTED_OUT.value
    mock_consent_log.method = consent_data["method"]
    mock_consent_log.message_sid = "SMmockmessageidoptout"
    mock_consent_log.created_at = datetime.now(timezone.utc)
    mock_consent_log.updated_at = datetime.now(timezone.utc)
    mock_consent_log.sent_at = datetime.now(timezone.utc)
    mock_consent_log.replied_at = datetime.now(timezone.utc)

    mock_consent_service_for_routes.handle_opt_out = AsyncMock(return_value=mock_consent_log)

    # Act
    response = test_app_client_fixture.post("/consent/opt-out", json=consent_data)

    # Assert
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["customer_id"] == consent_data["customer_id"]
    assert json_response["status"] == OptInStatus.OPTED_OUT.value
    mock_consent_service_for_routes.handle_opt_out.assert_called_once_with(
        phone_number=consent_data["phone_number"],
        customer_id=consent_data["customer_id"],
        business_id=consent_data["business_id"]
    )

def test_check_consent_status_true(test_app_client_fixture: TestClient, mock_consent_service_for_routes: MagicMock, mock_current_user_fixture: BusinessProfile):
    # Arrange
    phone_number = "+11234567890"
    business_id = mock_current_user_fixture.id

    mock_consent_service_for_routes.check_consent = AsyncMock(return_value=True)

    # Act
    response = test_app_client_fixture.get(f"/consent/status/{phone_number}/{business_id}")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"has_consent": True}
    mock_consent_service_for_routes.check_consent.assert_called_once_with(phone_number=phone_number, business_id=business_id)

def test_check_consent_status_false(test_app_client_fixture: TestClient, mock_consent_service_for_routes: MagicMock, mock_current_user_fixture: BusinessProfile):
    # Arrange
    phone_number = "+11234567890"
    business_id = mock_current_user_fixture.id

    mock_consent_service_for_routes.check_consent = AsyncMock(return_value=False)

    # Act
    response = test_app_client_fixture.get(f"/consent/status/{phone_number}/{business_id}")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"has_consent": False}
    mock_consent_service_for_routes.check_consent.assert_called_once_with(phone_number=phone_number, business_id=business_id)

def test_check_consent_status_service_error(test_app_client_fixture: TestClient, mock_consent_service_for_routes: MagicMock, mock_current_user_fixture: BusinessProfile):
    # Arrange
    phone_number = "+11234567890"
    business_id = mock_current_user_fixture.id

    mock_consent_service_for_routes.check_consent = AsyncMock(side_effect=HTTPException(status_code=500, detail="Service error"))

    # Act
    response = test_app_client_fixture.get(f"/consent/status/{phone_number}/{business_id}")

    # Assert
    assert response.status_code == 500
    assert response.json() == {"detail": "500: Service error"}

def test_get_consent_logs_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock, mock_current_user_fixture: BusinessProfile):
    # Arrange
    business_id = mock_current_user_fixture.id
    mock_log_1 = MagicMock(spec=ConsentLog)
    mock_log_1.id = 1
    mock_log_1.customer_id = 1
    mock_log_1.business_id = business_id
    mock_log_1.phone_number = "+1112223333"
    mock_log_1.status = OptInStatus.OPTED_IN.value
    mock_log_1.method = "api_test"
    mock_log_1.message_sid = "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    mock_log_1.created_at = datetime.now(timezone.utc)
    mock_log_1.updated_at = datetime.now(timezone.utc)
    mock_log_1.sent_at = datetime.now(timezone.utc)
    mock_log_1.replied_at = datetime.now(timezone.utc)

    mock_logs = [mock_log_1]

    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_offset = MagicMock()
    mock_limit = MagicMock()

    mock_db_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_filter
    mock_filter.offset.return_value = mock_offset
    mock_offset.limit.return_value = mock_limit
    mock_limit.all.return_value = mock_logs

    # Act
    response = test_app_client_fixture.get(f"/consent/logs/{business_id}")

    # Assert
    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 1
    assert json_response[0]["id"] == mock_log_1.id

    mock_db_session.query.assert_called_once_with(ConsentLog)

def test_get_consent_logs_empty(test_app_client_fixture: TestClient, mock_db_session: MagicMock, mock_current_user_fixture: BusinessProfile):
    # Arrange
    business_id = mock_current_user_fixture.id
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_offset = MagicMock()
    mock_limit = MagicMock()

    mock_db_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_filter
    mock_filter.offset.return_value = mock_offset
    mock_offset.limit.return_value = mock_limit
    mock_limit.all.return_value = []

    # Act
    response = test_app_client_fixture.get(f"/consent/logs/{business_id}")

    # Assert
    assert response.status_code == 200
    assert response.json() == []

def test_resend_opt_in_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock, mock_consent_service_for_routes: MagicMock, mock_current_user_fixture: BusinessProfile):
    # Arrange
    customer_id = 1
    expected_customer_business_id = mock_current_user_fixture.id
    expected_customer_phone = "+1234567899"

    mock_customer_instance = MagicMock()
    mock_customer_instance.id = customer_id
    mock_customer_instance.business_id = expected_customer_business_id
    mock_customer_instance.phone = expected_customer_phone

    query_mock_customer = MagicMock()
    filter_mock_customer = MagicMock()
    filter_mock_customer.first.return_value = mock_customer_instance
    query_mock_customer.filter.return_value = filter_mock_customer

    query_mock_business = MagicMock()
    filter_mock_business = MagicMock()
    mock_business_instance_for_route = MagicMock(spec=BusinessProfile)
    mock_business_instance_for_route.id = expected_customer_business_id
    mock_business_instance_for_route.representative_name = "Test Rep"
    mock_business_instance_for_route.business_name = "Test Business Name"
    mock_business_instance_for_route.twilio_number = "+15005550006"
    filter_mock_business.first.return_value = mock_business_instance_for_route
    query_mock_business.filter.return_value = filter_mock_business

    def query_side_effect(model_class):
        if model_class == Customer:
            return query_mock_customer
        elif model_class == BusinessProfile:
            return query_mock_business
        return MagicMock()

    mock_db_session.query.side_effect = query_side_effect

    mock_consent_service_for_routes.send_opt_in_sms = AsyncMock(return_value={"success": True, "message_sid": "SMmockresend"})

    # Act
    response = test_app_client_fixture.post(f"/consent/resend-optin/{customer_id}")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"message": "Opt-in request resent successfully"}
    mock_consent_service_for_routes.send_opt_in_sms.assert_called_once_with(
        phone_number=mock_customer_instance.phone,
        business_id=mock_business_instance_for_route.id,
        customer_id=mock_customer_instance.id
    )
    query_mock_customer.filter.assert_called_once()
    query_mock_business.filter.assert_called_once()


def test_resend_opt_in_customer_not_found(test_app_client_fixture: TestClient, mock_db_session: MagicMock, mock_consent_service_for_routes: MagicMock):
    # Arrange
    customer_id = 999

    query_mock_customer_not_found = MagicMock()
    filter_mock_customer_not_found = MagicMock()
    filter_mock_customer_not_found.first.return_value = None
    query_mock_customer_not_found.filter.return_value = filter_mock_customer_not_found

    original_query_side_effect = mock_db_session.query.side_effect
    def temp_query_side_effect_not_found(model_class):
        if model_class == Customer:
            return query_mock_customer_not_found
        if hasattr(original_query_side_effect, '__call__') and original_query_side_effect is not None :
             return original_query_side_effect(model_class)
        return MagicMock()
    mock_db_session.query.side_effect = temp_query_side_effect_not_found

    # Act
    response = test_app_client_fixture.post(f"/consent/resend-optin/{customer_id}")

    # Assert
    assert response.status_code == 404
    assert response.json() == {"detail": "Customer not found"}
    query_mock_customer_not_found.filter.assert_called_once()
    mock_db_session.query.side_effect = original_query_side_effect


def test_resend_opt_in_service_failure(test_app_client_fixture: TestClient, mock_db_session: MagicMock, mock_consent_service_for_routes: MagicMock, mock_current_user_fixture: BusinessProfile):
    # Arrange
    customer_id = 1
    expected_customer_business_id = mock_current_user_fixture.id
    expected_customer_phone = "+1234560000"

    mock_customer_instance = MagicMock()
    mock_customer_instance.id = customer_id
    mock_customer_instance.business_id = expected_customer_business_id
    mock_customer_instance.phone = expected_customer_phone

    query_mock_customer = MagicMock()
    filter_mock_customer = MagicMock()
    filter_mock_customer.first.return_value = mock_customer_instance
    query_mock_customer.filter.return_value = filter_mock_customer

    query_mock_business = MagicMock()
    filter_mock_business = MagicMock()
    mock_business_instance_for_route = MagicMock(spec=BusinessProfile)
    mock_business_instance_for_route.id = expected_customer_business_id
    mock_business_instance_for_route.representative_name = "Test Rep"
    mock_business_instance_for_route.business_name = "Test Business Name"
    mock_business_instance_for_route.twilio_number = "+15005550006"
    filter_mock_business.first.return_value = mock_business_instance_for_route
    query_mock_business.filter.return_value = filter_mock_business

    def query_side_effect(model_class):
        if model_class == Customer:
            return query_mock_customer
        elif model_class == BusinessProfile:
            return query_mock_business
        return MagicMock()

    mock_db_session.query.side_effect = query_side_effect

    # Configure mock to raise HTTPException directly
    mock_consent_service_for_routes.send_opt_in_sms = AsyncMock(
        side_effect=HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="UNIQUE_MOCK_SERVICE_FAILURE_XYZ" # This triggers the route's except block
        )
    )

    # Act
    response = test_app_client_fixture.post(f"/consent/resend-optin/{customer_id}")

    # Assert
    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to resend opt-in request"} # Route's generic error
    # Assertions for filter calls remain, they should still be called.
    query_mock_customer.filter.assert_called_once()
    query_mock_business.filter.assert_called_once()

# Final newline for PEP8
