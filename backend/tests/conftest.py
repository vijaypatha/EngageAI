import sys # Added
import os # Added
# Add project root to sys.path to allow imports like 'from backend.app...'
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.app.database import Base # Corrected import
from backend.app.models import BusinessProfile, Customer  # Corrected import
from unittest.mock import MagicMock

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
# sys.path modification at the top of the file should handle path discovery for 'backend.main'

@pytest.fixture(scope="session") # Using session scope
def test_app_client_fixture():
    # Imports app here to delay loading until fixture is used.
    # This can help with issues related to model loading order or app configuration.
    from backend.main import app # This import path is correct
    with TestClient(app) as client:
        yield client
