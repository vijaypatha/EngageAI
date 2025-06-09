# sys.path modifications removed
import pytest # Ensure pytest is imported
# import os # Not needed if sys.path block is removed
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

# Imports adjusted for running pytest from backend/
from app.models import Message as MessageModel # Changed
from app.models import BusinessProfile # Changed
from app.schemas import Message, MessageCreate, MessageUpdate # Changed
from app.database import get_db # Changed
from app.auth import get_current_user # Changed

@pytest.fixture(autouse=True)
def setup_api_test_overrides(mock_db_session: MagicMock, mock_current_user_fixture: BusinessProfile):
    from main import app as main_app_for_overrides # Changed from backend.main
    main_app_for_overrides.dependency_overrides[get_db] = lambda: mock_db_session
    main_app_for_overrides.dependency_overrides[get_current_user] = lambda: mock_current_user_fixture
    yield
    main_app_for_overrides.dependency_overrides.clear()

# Test Cases for Message Routes

def test_create_message_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock, mock_current_user_fixture: BusinessProfile): # Added test_app_client_fixture
    # Arrange
    message_data = {
        "conversation_id": "some-uuid-string", # Assuming UUID is stored as string if not converted
        "business_id": mock_current_user_fixture.id, # Ensure business_id matches current_user or is authorized
        "customer_id": 1,
        "content": "Hello from test_create_message_success",
        "message_type": "outbound",
        # status, parent_id, scheduled_time, sent_at, is_hidden, message_metadata can be omitted if optional
    }
    # The route uses MessageModel(**message.model_dump())
    # The mock_db_session.add() will receive an instance of MessageModel.
    # The from_orm call will be on this instance.

    # To simulate the object returned after db.refresh(db_message)
    # we can have `add` or `refresh` return a mock that has an `id` and other fields.
    # Or, more simply, ensure the mock passed to add is mutated or that from_orm works with MagicMock.

    # Let's make the mock_db_session.refresh fill in an ID for from_orm
    def mock_refresh(instance):
        if not hasattr(instance, 'id') or instance.id is None:
            instance.id = 123 # Simulate ID assignment by DB
        # For other fields that might be auto-generated or default in DB:
        if not hasattr(instance, 'created_at') or instance.created_at is None:
            from datetime import datetime, timezone
            instance.created_at = datetime.now(timezone.utc)


    mock_db_session.refresh = MagicMock(side_effect=mock_refresh)
    # add and commit usually don't need specific return values for this kind of test
    mock_db_session.add = MagicMock()
    mock_db_session.commit = MagicMock()

    # Act
    response = test_app_client_fixture.post("/messages/", json=message_data) # Used fixture

    # Assert
    assert response.status_code == 200 # The route returns Message, typically 200 for POST if not specified 201
    json_response = response.json()
    assert json_response["id"] == 123 # From mock_refresh
    assert json_response["content"] == message_data["content"]
    assert json_response["business_id"] == message_data["business_id"]

    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()


def test_create_message_validation_error(test_app_client_fixture: TestClient): # Added test_app_client_fixture
    # Arrange - payload missing required fields (e.g., content)
    # MessageCreate schema likely requires content, conversation_id, business_id, customer_id, message_type
    invalid_payload = {
        "conversation_id": "some-uuid",
        # "content": "missing",
    }
    # Act
    response = test_app_client_fixture.post("/messages/", json=invalid_payload) # Used fixture
    # Assert
    assert response.status_code == 422 # FastAPI validation error


def test_get_messages_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock): # Added test_app_client_fixture
    # Arrange
    mock_msg1_model = MagicMock(spec=MessageModel)
    mock_msg1_model.id = 1; mock_msg1_model.content = "Msg1"
    # Add all fields Message.from_orm would access
    from datetime import datetime, timezone
    mock_msg1_model.conversation_id = "uuid1"; mock_msg1_model.business_id = 1; mock_msg1_model.customer_id = 1;
    mock_msg1_model.message_type = "outbound"; mock_msg1_model.status = "sent"; mock_msg1_model.created_at = datetime.now(timezone.utc)


    mock_msg2_model = MagicMock(spec=MessageModel)
    mock_msg2_model.id = 2; mock_msg2_model.content = "Msg2"
    mock_msg2_model.conversation_id = "uuid2"; mock_msg2_model.business_id = 1; mock_msg2_model.customer_id = 2;
    mock_msg2_model.message_type = "inbound"; mock_msg2_model.status = "delivered"; mock_msg2_model.created_at = datetime.now(timezone.utc)

    mock_db_session.query(MessageModel).offset(0).limit(100).all.return_value = [mock_msg1_model, mock_msg2_model]

    # Act
    response = test_app_client_fixture.get("/messages/?skip=0&limit=10") # Used fixture

    # Assert
    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 2
    assert json_response[0]["id"] == 1
    assert json_response[1]["content"] == "Msg2"


def test_get_messages_empty(test_app_client_fixture: TestClient, mock_db_session: MagicMock): # Added test_app_client_fixture
    # Arrange
    mock_db_session.query(MessageModel).offset(0).limit(100).all.return_value = []
    # Act
    response = test_app_client_fixture.get("/messages/") # Used fixture
    # Assert
    assert response.status_code == 200
    assert response.json() == []


def test_get_message_by_id_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock): # Added test_app_client_fixture
    # Arrange
    message_id = 1
    mock_msg_model = MagicMock(spec=MessageModel)
    mock_msg_model.id = message_id; mock_msg_model.content = "Specific Message"
    from datetime import datetime, timezone
    mock_msg_model.conversation_id = "uuid1"; mock_msg_model.business_id = 1; mock_msg_model.customer_id = 1;
    mock_msg_model.message_type = "outbound"; mock_msg_model.status = "sent"; mock_msg_model.created_at = datetime.now(timezone.utc)


    mock_db_session.query(MessageModel).filter().first.return_value = mock_msg_model
    # Act
    response = test_app_client_fixture.get(f"/messages/{message_id}") # Used fixture
    # Assert
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["id"] == message_id
    assert json_response["content"] == "Specific Message"


def test_get_message_by_id_not_found(test_app_client_fixture: TestClient, mock_db_session: MagicMock): # Added test_app_client_fixture
    # Arrange
    non_existent_message_id = 999
    mock_db_session.query(MessageModel).filter().first.return_value = None
    # Act
    response = test_app_client_fixture.get(f"/messages/{non_existent_message_id}") # Used fixture
    # Assert
    assert response.status_code == 404
    assert response.json() == {"detail": "Message not found"}


def test_update_message_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock): # Added test_app_client_fixture
    # Arrange
    message_id = 1
    update_data = {"content": "Updated content", "status": "read"}

    mock_existing_msg = MagicMock(spec=MessageModel)
    mock_existing_msg.id = message_id
    mock_existing_msg.content = "Original content"
    mock_existing_msg.status = "sent"
    # Add other fields needed for from_orm
    from datetime import datetime, timezone
    mock_existing_msg.conversation_id = "uuid1"; mock_existing_msg.business_id = 1; mock_existing_msg.customer_id = 1;
    mock_existing_msg.message_type = "outbound"; mock_existing_msg.created_at = datetime.now(timezone.utc)


    mock_db_session.query(MessageModel).filter().first.return_value = mock_existing_msg
    mock_db_session.commit = MagicMock()
    mock_db_session.refresh = MagicMock()

    # Act
    response = test_app_client_fixture.put(f"/messages/{message_id}", json=update_data) # Used fixture

    # Assert
    assert response.status_code == 200
    # Check that setattr was called on the mock_existing_msg (or that its attributes changed)
    # The route code does: for field, value in message.model_dump(exclude_unset=True).items(): setattr(db_message, field, value)
    assert mock_existing_msg.content == "Updated content"
    assert mock_existing_msg.status == "read"

    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(mock_existing_msg)

    json_response = response.json()
    assert json_response["content"] == "Updated content"
    assert json_response["status"] == "read"


def test_update_message_not_found(test_app_client_fixture: TestClient, mock_db_session: MagicMock): # Added test_app_client_fixture
    # Arrange
    message_id = 999
    update_data = {"content": "Doesn't matter"}
    mock_db_session.query(MessageModel).filter().first.return_value = None
    # Act
    response = test_app_client_fixture.put(f"/messages/{message_id}", json=update_data) # Used fixture
    # Assert
    assert response.status_code == 404
    assert response.json() == {"detail": "Message not found"}


def test_delete_message_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock): # Added test_app_client_fixture
    # Arrange
    message_id = 1
    mock_msg_to_delete = MagicMock(spec=MessageModel)
    mock_msg_to_delete.id = message_id

    mock_db_session.query(MessageModel).filter().first.return_value = mock_msg_to_delete
    mock_db_session.delete = MagicMock()
    mock_db_session.commit = MagicMock()

    # Act
    response = test_app_client_fixture.delete(f"/messages/{message_id}") # Used fixture

    # Assert
    assert response.status_code == 200
    assert response.json() == {"message": "Message deleted successfully"}
    mock_db_session.delete.assert_called_once_with(mock_msg_to_delete)
    mock_db_session.commit.assert_called_once()


def test_delete_message_not_found(test_app_client_fixture: TestClient, mock_db_session: MagicMock): # Added test_app_client_fixture
    # Arrange
    message_id = 999
    mock_db_session.query(MessageModel).filter().first.return_value = None
    # Act
    response = test_app_client_fixture.delete(f"/messages/{message_id}") # Used fixture
    # Assert
    assert response.status_code == 404
    assert response.json() == {"detail": "Message not found"}

# Final newline for PEP8
