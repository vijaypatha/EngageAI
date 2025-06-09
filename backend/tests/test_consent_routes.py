# sys.path modifications removed
import pytest # Ensure pytest is imported
# import os # Not needed if sys.path block is removed
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

# Imports adjusted for running pytest from backend/
from app.models import BusinessProfile, Customer, ConsentLog, OptInStatus # Changed
from app.schemas import ConsentResponse, ConsentStatusResponse, OptInRequest, OptOutRequest, ResendOptInRequest # Changed
from app.database import get_db # Changed
from app.auth import get_current_user # Changed
from app.services.consent_service import ConsentService # Changed

@pytest.fixture(autouse=True)
def setup_api_test_overrides(mock_db_session: MagicMock, mock_current_user_fixture: BusinessProfile):
    from main import app as main_app_for_overrides # Changed from backend.main
    main_app_for_overrides.dependency_overrides[get_db] = lambda: mock_db_session
    main_app_for_overrides.dependency_overrides[get_current_user] = lambda: mock_current_user_fixture
    yield
    main_app_for_overrides.dependency_overrides.clear()

# Test Cases

def test_opt_in_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock, mock_current_user_fixture: BusinessProfile):
    # Arrange
    consent_data = {"phone_number": "1234567890", "business_id": mock_current_user_fixture.id, "customer_id": 1}
    mock_consent_log = MagicMock(spec=ConsentLog)
    mock_consent_log.id = 1
    mock_consent_log.customer_id = consent_data["customer_id"]
    mock_consent_log.business_id = consent_data["business_id"]
    mock_consent_log.phone_number = consent_data["phone_number"]
    mock_consent_log.status = OptInStatus.OPTED_IN.value
    mock_consent_log.method = "api_request"

    mock_service_instance = MagicMock(spec=ConsentService)
    mock_service_instance.handle_opt_in = AsyncMock(return_value=mock_consent_log)

    with patch('app.routes.consent_routes.get_consent_service') as mock_get_service: # Changed patch path
        mock_get_service.return_value = mock_service_instance

        # Act
        response = test_app_client_fixture.post("/consent/opt-in", json=consent_data) # Used fixture

    # Assert
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["customer_id"] == consent_data["customer_id"]
    assert json_response["status"] == OptInStatus.OPTED_IN.value
    mock_service_instance.handle_opt_in.assert_called_once_with(
        customer_id=consent_data["customer_id"],
        business_id=consent_data["business_id"],
        method_detail="API Opt-In" # Default from route
    )


def test_opt_in_service_error(test_app_client_fixture: TestClient, mock_current_user_fixture: BusinessProfile): # Added test_app_client_fixture
    # Arrange
    consent_data = {"phone_number": "1234567890", "business_id": mock_current_user_fixture.id, "customer_id": 1}

    mock_service_instance = MagicMock(spec=ConsentService)
    mock_service_instance.handle_opt_in = AsyncMock(side_effect=HTTPException(status_code=500, detail="Service Error"))

    with patch('app.routes.consent_routes.get_consent_service') as mock_get_service: # Changed patch path
        mock_get_service.return_value = mock_service_instance

        # Act
        response = test_app_client_fixture.post("/consent/opt-in", json=consent_data) # Used fixture

    # Assert
    assert response.status_code == 500
    assert response.json() == {"detail": "Service Error"}


def test_opt_out_success(test_app_client_fixture: TestClient, mock_current_user_fixture: BusinessProfile): # Added test_app_client_fixture
    # Arrange
    consent_data = {"phone_number": "1234567890", "business_id": mock_current_user_fixture.id, "customer_id": 1}
    mock_consent_log = MagicMock(spec=ConsentLog)
    mock_consent_log.id = 2
    mock_consent_log.customer_id = consent_data["customer_id"]
    mock_consent_log.business_id = consent_data["business_id"]
    mock_consent_log.phone_number = consent_data["phone_number"]
    mock_consent_log.status = OptInStatus.OPTED_OUT.value
    mock_consent_log.method = "api_request"

    mock_service_instance = MagicMock(spec=ConsentService)
    mock_service_instance.handle_opt_out = AsyncMock(return_value=mock_consent_log)

    with patch('app.routes.consent_routes.get_consent_service') as mock_get_service: # Changed patch path
        mock_get_service.return_value = mock_service_instance

        # Act
        response = test_app_client_fixture.post("/consent/opt-out", json=consent_data) # Used fixture

    # Assert
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["customer_id"] == consent_data["customer_id"]
    assert json_response["status"] == OptInStatus.OPTED_OUT.value
    mock_service_instance.handle_opt_out.assert_called_once_with(
        customer_id=consent_data["customer_id"],
        business_id=consent_data["business_id"],
        method_detail="API Opt-Out" # Default from route
    )


def test_check_consent_status_true(test_app_client_fixture: TestClient, mock_current_user_fixture: BusinessProfile): # Added test_app_client_fixture
    # Arrange
    phone_number = "1234567890"
    business_id = mock_current_user_fixture.id

    mock_service_instance = MagicMock(spec=ConsentService)
    mock_service_instance.check_consent = AsyncMock(return_value=True)

    with patch('app.routes.consent_routes.get_consent_service') as mock_get_service: # Changed patch path
        mock_get_service.return_value = mock_service_instance

        # Act
        response = test_app_client_fixture.get(f"/consent/status/{phone_number}/{business_id}") # Used fixture

    # Assert
    assert response.status_code == 200
    assert response.json() == {"has_consent": True}
    mock_service_instance.check_consent.assert_called_once_with(phone_number=phone_number, business_id=business_id)


def test_check_consent_status_false(test_app_client_fixture: TestClient, mock_current_user_fixture: BusinessProfile): # Added test_app_client_fixture
    # Arrange
    phone_number = "1234567890"
    business_id = mock_current_user_fixture.id

    mock_service_instance = MagicMock(spec=ConsentService)
    mock_service_instance.check_consent = AsyncMock(return_value=False)

    with patch('app.routes.consent_routes.get_consent_service') as mock_get_service: # Changed patch path
        mock_get_service.return_value = mock_service_instance

        # Act
        response = test_app_client_fixture.get(f"/consent/status/{phone_number}/{business_id}") # Used fixture

    # Assert
    assert response.status_code == 200
    assert response.json() == {"has_consent": False}


def test_check_consent_status_service_error(test_app_client_fixture: TestClient, mock_current_user_fixture: BusinessProfile): # Added test_app_client_fixture
    # Arrange
    phone_number = "1234567890"
    business_id = mock_current_user_fixture.id

    mock_service_instance = MagicMock(spec=ConsentService)
    mock_service_instance.check_consent = AsyncMock(side_effect=HTTPException(status_code=500, detail="Service error"))

    with patch('app.routes.consent_routes.get_consent_service') as mock_get_service: # Changed patch path
        mock_get_service.return_value = mock_service_instance

        # Act
        response = test_app_client_fixture.get(f"/consent/status/{phone_number}/{business_id}") # Used fixture

    # Assert
    assert response.status_code == 500
    assert response.json() == {"detail": "Service error"}


def test_get_consent_logs_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock, mock_current_user_fixture: BusinessProfile): # Added test_app_client_fixture
    # Arrange
    business_id = mock_current_user_fixture.id
    mock_log_1 = MagicMock(spec=ConsentLog)
    mock_log_1.id = 1; mock_log_1.customer_id = 1; mock_log_1.business_id = business_id; mock_log_1.phone_number="111"; mock_log_1.status="opted_in"; mock_log_1.method="api"
    # Make it suitable for ConsentResponse.from_orm
    # For from_orm to work on a MagicMock, the attributes must exist.
    # For simplicity, we can also mock the from_orm call if the object is complex,
    # or ensure the mock has all fields ConsentResponse might access.
    # Here, we assume ConsentResponse primarily uses fields directly from ConsentLog.

    mock_logs = [mock_log_1]

    # Mock the query chain for fetching logs
    # The route does: db.query(ConsentLog).filter(ConsentLog.business_id == business_id, ConsentLog.customer_id == customer_id).offset(skip).limit(limit).all()
    # The prompt test is for /logs/{business_id}, so no customer_id in filter
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
    response = test_app_client_fixture.get(f"/consent/logs/{business_id}") # Used fixture

    # Assert
    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 1
    assert json_response[0]["id"] == mock_log_1.id # Example check

    mock_db_session.query.assert_called_once_with(ConsentLog)
    # Check that filter was called with business_id
    # Cannot directly check filter call args easily with chained mocks this way without more complex setup.
    # Trusting the mock chain for now. A more robust way is to check args of mock_query.filter.


def test_get_consent_logs_empty(test_app_client_fixture: TestClient, mock_db_session: MagicMock, mock_current_user_fixture: BusinessProfile): # Added test_app_client_fixture
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
    response = test_app_client_fixture.get(f"/consent/logs/{business_id}") # Used fixture

    # Assert
    assert response.status_code == 200
    assert response.json() == []


def test_resend_opt_in_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock, mock_current_user_fixture: BusinessProfile): # Added test_app_client_fixture
    # Arrange
    customer_id = 1
    mock_customer_instance = MagicMock(spec=Customer)
    mock_customer_instance.id = customer_id
    mock_customer_instance.business_id = mock_current_user_fixture.id

    # Mock DB query for customer
    mock_db_session.query(Customer).filter().first.return_value = mock_customer_instance
    # Mock DB query for business (done by get_current_user fixture)

    mock_service_instance = MagicMock(spec=ConsentService)
    # Assuming send_double_optin_sms is the correct method from previous tests
    mock_service_instance.send_double_optin_sms = AsyncMock(return_value={"success": True, "message_sid": "SMxxxx"})

    with patch('app.routes.consent_routes.get_consent_service') as mock_get_service: # Changed patch path
        mock_get_service.return_value = mock_service_instance

        # Act (customer_id is a path parameter, no JSON body for this POST)
        response = test_app_client_fixture.post(f"/consent/resend-optin/{customer_id}") # Used fixture

    # Assert
    assert response.status_code == 200
    assert response.json() == {"message": "Opt-in request resent successfully."} # Match exact message from route
    mock_service_instance.send_double_optin_sms.assert_called_once_with(
        customer_id=customer_id,
        business_id=mock_current_user_fixture.id
    )


def test_resend_opt_in_customer_not_found(test_app_client_fixture: TestClient, mock_db_session: MagicMock): # Added test_app_client_fixture
    # Arrange
    customer_id = 999 # Non-existent
    mock_db_session.query(Customer).filter().first.return_value = None

    # Act
    response = test_app_client_fixture.post(f"/consent/resend-optin/{customer_id}") # Used fixture

    # Assert
    assert response.status_code == 404
    assert response.json() == {"detail": "Customer not found"}


def test_resend_opt_in_service_failure(test_app_client_fixture: TestClient, mock_db_session: MagicMock, mock_current_user_fixture: BusinessProfile): # Added test_app_client_fixture
    # Arrange
    customer_id = 1
    mock_customer_instance = MagicMock(spec=Customer)
    mock_customer_instance.id = customer_id
    mock_customer_instance.business_id = mock_current_user_fixture.id
    mock_db_session.query(Customer).filter().first.return_value = mock_customer_instance

    mock_service_instance = MagicMock(spec=ConsentService)
    mock_service_instance.send_double_optin_sms = AsyncMock(return_value={"success": False, "message": "Twilio down"})
    # Or mock_service_instance.send_double_optin_sms = AsyncMock(side_effect=Exception("Service internal error"))
    # The route checks for `if not result.get("success")`.

    with patch('app.routes.consent_routes.get_consent_service') as mock_get_service: # Changed patch path
        mock_get_service.return_value = mock_service_instance

        # Act
        response = test_app_client_fixture.post(f"/consent/resend-optin/{customer_id}") # Used fixture

    # Assert
    assert response.status_code == 500 # As per route's handling of service failure
    assert response.json() == {"detail": "Failed to resend opt-in request. Reason: Twilio down"}

# Final newline for PEP8
