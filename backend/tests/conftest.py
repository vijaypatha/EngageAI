import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session # Added Session
from app.database import Base
from app.models import BusinessProfile, Customer  # Import models
import os
from unittest.mock import MagicMock # Import MagicMock

# Use SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}  # Needed for SQLite
    )
    # Base.metadata.create_all(bind=engine) # Moved to db fixture
    yield engine
    # Base.metadata.drop_all(bind=engine) # Moved to db fixture
    if os.path.exists("./test.db"): # Ensure this is still here
        os.remove("./test.db")

@pytest.fixture(scope="function")
def db(engine): # Renamed db_session to db for consistency with original
    """Creates a new database session for each test function, dropping and recreating tables."""
    # Drop all tables first
    Base.metadata.drop_all(bind=engine)
    # Create all tables
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_session = TestingSessionLocal() # Use a distinct variable name db_session internally
    try:
        yield db_session
    finally:
        db_session.rollback()
        db_session.close()

@pytest.fixture(scope="function")
def mock_db_session():
    """Returns a MagicMock instance with the spec of sqlalchemy.orm.Session."""
    mock = MagicMock(spec=Session)
    return mock

@pytest.fixture(scope="function")
def mock_business(db: Session): # Changed db_session to db for parameter name
    """Creates and returns a BusinessProfile ORM instance using the db fixture."""
    business = BusinessProfile(
        business_name="Test Business",
        industry="Tech",
        business_goal="Test Goal",
        primary_services="Testing Services",
        representative_name="Test Rep",
        timezone="UTC"
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    return business

@pytest.fixture(scope="function")
def mock_customer(db: Session, mock_business: BusinessProfile): # Changed db_session to db
    """Creates and returns a Customer ORM instance using the db fixture and mock_business."""
    customer = Customer(
        customer_name="Test Customer",
        phone="1234567890",
        lifecycle_stage="Lead",
        business_id=mock_business.id
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer

@pytest.fixture(scope="function")
def mock_current_user_fixture():
    """Returns a mock BusinessProfile object for API tests."""
    mock_user = MagicMock(spec=BusinessProfile)
    mock_user.id = 1
    mock_user.business_name = "Mocked Business"
    return mock_user

# Added TestClient and app import for the new fixture
from fastapi.testclient import TestClient
# Ensure sys.path is set up for this import if conftest is run directly or in certain contexts.
# However, pytest usually handles path discovery well for conftest.
# If `backend` is not found, `sys.path` modification might be needed here too,
# or ensure tests are run from project root. For now, assume direct import works.

@pytest.fixture(scope="session") # Using session scope
def test_app_client_fixture():
    # Imports app here to delay loading until fixture is used.
    # This can help with issues related to model loading order or app configuration.
    from backend.main import app # Corrected import path for app
    with TestClient(app) as client:
        yield client
