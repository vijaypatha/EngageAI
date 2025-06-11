import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, ANY
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, date, time

# Imports from app
from app.routes.business_routes import slugify
from app.models import BusinessProfile as BusinessProfileModel
from app.schemas import BusinessProfile as BusinessProfileSchema
from app.schemas import BusinessProfileCreate, BusinessProfileUpdate
from app.database import get_db
from fastapi import status

# Test slugify function directly
@pytest.mark.parametrize("name, expected_slug", [
    ("Test Business Name", "test-business-name"),
    ("  Leading & Trailing Spaces  ", "leading-trailing-spaces"),
    ("Special!@#Chars", "specialchars"),
    ("UPPERCASE NAME", "uppercase-name"),
    ("Name with -- multiple --- hyphens", "name-with-multiple-hyphens"),
    ("Single", "single"),
    (None, ""),
    ("", ""),
    ("  ", ""),
    ("-name-starts-ends-hyphen-", "name-starts-ends-hyphen"),
])
def test_slugify_function(name, expected_slug):
    assert slugify(name) == expected_slug

# Autouse fixture for dependency overrides
@pytest.fixture(autouse=True)
def setup_business_routes_test_overrides(
    test_app_client_fixture: TestClient,
    mock_db_session: MagicMock
):
    app_instance = test_app_client_fixture.app
    app_instance.dependency_overrides[get_db] = lambda: mock_db_session
    yield
    app_instance.dependency_overrides.clear()

def test_create_business_profile_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    request_payload = {
        "business_name": "My New Business", "industry": "Tech",
        "business_goal": "Grow customer base", "primary_services": "Software Development",
        "representative_name": "John Doe",
        "business_phone_number": "+15551234567", "timezone": "America/New_York",
        "review_platform_url": "https://reviews.example.com"
        # email, website, social_media_links, enable_ai_faq_auto_reply, notify_owner_on_reply_with_link
        # are not in BusinessProfileCreate, so ORM defaults (False, False for booleans) will apply.
    }

    mock_db_session.query(BusinessProfileModel).filter(ANY).first.return_value = None

    def mock_add_and_refresh_side_effect(instance_passed_to_db):
        instance_passed_to_db.id = 1
        instance_passed_to_db.created_at = datetime.utcnow()
        instance_passed_to_db.updated_at = datetime.utcnow()
        # Ensure ORM defaults are reflected if not in payload (already handled by model)
        # For assertion purposes, ensure these are set as expected by the response model
        if not hasattr(instance_passed_to_db, 'notify_owner_on_reply_with_link') or instance_passed_to_db.notify_owner_on_reply_with_link is None :
             instance_passed_to_db.notify_owner_on_reply_with_link = False
        if not hasattr(instance_passed_to_db, 'enable_ai_faq_auto_reply') or instance_passed_to_db.enable_ai_faq_auto_reply is None:
             instance_passed_to_db.enable_ai_faq_auto_reply = False

    mock_db_session.add = MagicMock(side_effect=mock_add_and_refresh_side_effect)
    mock_db_session.commit = MagicMock()
    mock_db_session.refresh = MagicMock()

    response = test_app_client_fixture.post("/business-profile/", json=request_payload)

    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert response_data["business_name"] == request_payload["business_name"]
    assert response_data["slug"] == "my-new-business"
    assert response_data["id"] == 1
    assert response_data["notify_owner_on_reply_with_link"] is False
    assert response_data["enable_ai_faq_auto_reply"] is False

    mock_db_session.add.assert_called_once()
    added_instance_arg = mock_db_session.add.call_args[0][0]
    assert added_instance_arg.business_name == request_payload["business_name"]
    assert added_instance_arg.slug == "my-new-business"
    assert added_instance_arg.notify_owner_on_reply_with_link is False
    assert added_instance_arg.enable_ai_faq_auto_reply is False
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(added_instance_arg)


def test_create_business_profile_name_conflict(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    business_data = {
        "business_name": "Existing Business", "industry": "Retail",
        "business_goal": "Goal", "primary_services": "Services",
        "representative_name": "Rep"
    }
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.business_name == "Existing Business").first.return_value = BusinessProfileModel(id=1, business_name="Existing Business")

    response = test_app_client_fixture.post("/business-profile/", json=business_data)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "Business name already exists" in response.json()["detail"]

def test_create_business_profile_slug_conflict(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    business_data = {
        "business_name": "Another Business", "industry": "Food",
        "business_goal": "Goal", "primary_services": "Services",
        "representative_name": "Rep"
    }
    # Mock the .first() call to have a side effect list
    # First call (name check) returns None, second call (slug check) returns an existing profile
    mock_db_session.query(BusinessProfileModel).filter().first.side_effect = [
        None,
        BusinessProfileModel(id=2, slug="another-business", business_name="Some Other Name")
    ]

    response = test_app_client_fixture.post("/business-profile/", json=business_data)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "Generated slug 'another-business' from business name already exists. Please try a slightly different business name." in response.json()["detail"]


def test_create_business_profile_integrity_error_on_commit(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    business_data = {
        "business_name": "Yet Another Business", "industry": "Consulting",
        "business_goal": "Goal", "primary_services": "Services",
        "representative_name": "Rep"
    }
    mock_db_session.query(BusinessProfileModel).filter(ANY).first.return_value = None
    mock_db_session.commit.side_effect = IntegrityError("mocked integrity error", params=None, orig=None)
    mock_db_session.add = MagicMock()
    mock_db_session.rollback = MagicMock()
    response = test_app_client_fixture.post("/business-profile/", json=business_data)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "A business with this name or resulting slug already exists" in response.json()["detail"]
    mock_db_session.rollback.assert_called_once()

def test_create_business_profile_invalid_payload(test_app_client_fixture: TestClient):
    response = test_app_client_fixture.post("/business-profile/", json={"industry": "Tech"})
    assert response.status_code == 422

def create_mock_db_profile(_id, name, slug, **kwargs):
    orm_attributes = {
        "id": _id, "business_name": name, "slug": slug,
        "industry": "Test Industry", "primary_services": "Test Services",
        "business_goal": "Test Goal", "representative_name": "Test Rep",
        "business_phone_number": "+15550001111",
        "enable_ai_faq_auto_reply": False,
        "notify_owner_on_reply_with_link": False,
        "timezone": "UTC",
        "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
        "structured_faq_data": None, "review_platform_url": None,
        "twilio_number": None, "twilio_sid": None, "messaging_service_sid": None
    }
    for key, value in kwargs.items():
        if hasattr(BusinessProfileModel, key): # Check if it's a valid ORM attribute
            orm_attributes[key] = value

    mock_orm_instance = MagicMock(spec=BusinessProfileModel)
    for key, value in orm_attributes.items():
        setattr(mock_orm_instance, key, value)
    return mock_orm_instance

def test_get_business_profile_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_profile_orm = create_mock_db_profile(1, "Found Business", "found-business")
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.id == 1).first.return_value = mock_profile_orm
    response = test_app_client_fixture.get("/business-profile/1")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["id"] == 1
    assert response_data["business_name"] == "Found Business"
    assert "email" not in response_data
    assert "website" not in response_data

def test_get_business_profile_not_found(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.id == 999).first.return_value = None
    response = test_app_client_fixture.get("/business-profile/999")
    assert response.status_code == 404
    assert "Business profile not found" in response.json()["detail"]

def test_update_business_profile_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_profile = create_mock_db_profile(1, "Old Name", "old-name")
    # Simulate the two .first() calls in the route:
    # 1. Get profile by ID
    # 2. Check for slug conflict (if name changes) - return None for no conflict
    mock_db_session.query(BusinessProfileModel).filter(ANY).first.side_effect = [mock_profile, None]

    update_payload = {"business_name": "New Name", "industry": "Updated Industry", "enable_ai_faq_auto_reply": True}
    response = test_app_client_fixture.put("/business-profile/1", json=update_payload)

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["business_name"] == "New Name"
    assert response_data["industry"] == "Updated Industry"
    assert response_data["slug"] == "new-name"
    assert response_data["enable_ai_faq_auto_reply"] is True
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(mock_profile)
    assert mock_profile.business_name == "New Name"
    assert mock_profile.industry == "Updated Industry"
    assert mock_profile.enable_ai_faq_auto_reply is True

def test_update_business_profile_not_found(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.id == 999).first.return_value = None
    response = test_app_client_fixture.put("/business-profile/999", json={"business_name": "Non Existent"})
    assert response.status_code == 404

def test_update_business_profile_slug_conflict(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_profile_to_update = create_mock_db_profile(1, "Original Name", "original-name")
    mock_conflicting_profile = create_mock_db_profile(2, "Other Business", "new-name-slug")

    # Simulate the two .first() calls:
    # 1. Get profile by ID
    # 2. Check for slug conflict - return conflicting profile
    mock_db_session.query(BusinessProfileModel).filter(ANY).first.side_effect = [
        mock_profile_to_update,
        mock_conflicting_profile
    ]

    update_payload = {"business_name": "New Name Slug"}
    response = test_app_client_fixture.put("/business-profile/1", json=update_payload)
    assert response.status_code == 409
    assert "New business name generates a slug ('new-name-slug') that already exists." in response.json()["detail"]

def test_get_business_timezone_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_profile = create_mock_db_profile(1, "Timezone Biz", "timezone-biz", timezone="America/New_York")
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.id == 1).first.return_value = mock_profile
    response = test_app_client_fixture.get("/business-profile/1/timezone")
    assert response.status_code == 200
    assert response.json() == {"timezone": "America/New_York"}

def test_update_business_timezone_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_profile = create_mock_db_profile(1, "Timezone Biz", "timezone-biz", timezone="UTC")
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.id == 1).first.return_value = mock_profile
    response = test_app_client_fixture.put("/business-profile/1/timezone", json={"timezone": "Europe/London"})
    assert response.status_code == 200
    assert response.json() == {"timezone": "Europe/London"}
    mock_db_session.commit.assert_called_once()
    assert mock_profile.timezone == "Europe/London"

def test_get_business_id_by_name_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_id_obj = MagicMock()
    mock_id_obj.id = 5
    mock_db_session.query(BusinessProfileModel.id).filter(BusinessProfileModel.business_name == "Exact Name").first.return_value = mock_id_obj
    response = test_app_client_fixture.get("/business-profile/business-id/Exact Name")
    assert response.status_code == 200
    assert response.json() == {"business_id": 5}

def test_get_business_id_by_name_not_found(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_db_session.query(BusinessProfileModel.id).filter(BusinessProfileModel.business_name == "Unknown Name").first.return_value = None
    response = test_app_client_fixture.get("/business-profile/business-id/Unknown Name")
    assert response.status_code == 404

def test_get_business_id_by_slug_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_id_obj = MagicMock()
    mock_id_obj.id = 10
    mock_db_session.query(BusinessProfileModel.id).filter(BusinessProfileModel.slug == "found-slug").first.return_value = mock_id_obj
    response = test_app_client_fixture.get("/business-profile/business-id/slug/found-slug")
    assert response.status_code == 200
    assert response.json() == {"business_id": 10}

def test_get_navigation_profile_by_slug_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_profile_orm = create_mock_db_profile(12, "Nav Prof", "nav-prof-slug")
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.slug == "nav-prof-slug").first.return_value = mock_profile_orm
    response = test_app_client_fixture.get("/business-profile/navigation-profile/slug/nav-prof-slug")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["business_name"] == "Nav Prof"
    assert "email" not in response_data

def test_update_business_phone_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_profile = create_mock_db_profile(1, "Phone Update Biz", "phone-update")
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.id == 1).first.return_value = mock_profile
    new_phone = "+15559876543"
    response = test_app_client_fixture.patch("/business-profile/1/phone", json={"business_phone_number": new_phone})
    assert response.status_code == 200
    assert response.json()["business_phone_number"] == new_phone
    mock_db_session.commit.assert_called_once()
    assert mock_profile.business_phone_number == new_phone

def test_cleanup_abandoned_profiles_success(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_filtered_query = MagicMock()
    mock_filtered_query.delete = MagicMock(return_value=3)
    mock_db_session.query(BusinessProfileModel).filter.return_value = mock_filtered_query
    response = test_app_client_fixture.delete("/business-profile/abandoned")
    assert response.status_code == 200
    assert response.json() == {"message": "Deleted 3 abandoned profiles"}
    mock_db_session.commit.assert_called_once()

def test_cleanup_abandoned_profiles_none_deleted(test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    mock_filtered_query = MagicMock()
    mock_filtered_query.delete = MagicMock(return_value=0)
    mock_db_session.query(BusinessProfileModel).filter.return_value = mock_filtered_query
    response = test_app_client_fixture.delete("/business-profile/abandoned")
    assert response.status_code == 200
    assert response.json() == {"message": "Deleted 0 abandoned profiles"}


# --- Tests for Caching of Navigation Profile ---

@patch('app.routes.business_routes.redis_client', new_callable=MagicMock)
def test_get_navigation_profile_cache_miss_and_store(mock_redis_client, test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    # Arrange
    slug = "cache-miss-slug"
    cache_key = f"business_profile_nav_slug:{slug}"
    mock_redis_client.get.return_value = None # Cache miss

    mock_profile_orm = create_mock_db_profile(id=20, name="Cache Miss Test", slug=slug)
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first.return_value = mock_profile_orm

    expected_profile_data = BusinessProfileSchema.from_orm(mock_profile_orm)

    # Act
    response = test_app_client_fixture.get(f"/business-profile/navigation-profile/slug/{slug}")

    # Assert
    assert response.status_code == 200
    assert response.json()["business_name"] == "Cache Miss Test"
    mock_redis_client.get.assert_called_once_with(cache_key)
    mock_redis_client.set.assert_called_once_with(cache_key, expected_profile_data.model_dump_json(), ex=3600)
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first.assert_called_once()


@patch('app.routes.business_routes.redis_client', new_callable=MagicMock)
def test_get_navigation_profile_cache_hit(mock_redis_client, test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    # Arrange
    slug = "cache-hit-slug"
    cache_key = f"business_profile_nav_slug:{slug}"

    # Prepare mock profile data as it would be in cache (JSON string)
    mock_cached_profile = BusinessProfileSchema(
        id=21, business_name="Cached Biz", slug=slug, industry="Cache",
        business_goal="Hit Cache", primary_services="Caching", representative_name="Cache Rep",
        timezone="GMT", created_at=datetime.utcnow(), notify_owner_on_reply_with_link=False, enable_ai_faq_auto_reply=False
    )
    mock_redis_client.get.return_value = mock_cached_profile.model_dump_json()

    # Act
    response = test_app_client_fixture.get(f"/business-profile/navigation-profile/slug/{slug}")

    # Assert
    assert response.status_code == 200
    assert response.json()["business_name"] == "Cached Biz"
    mock_redis_client.get.assert_called_once_with(cache_key)
    mock_redis_client.set.assert_not_called() # Should not set if cache hit
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first.assert_not_called() # DB should not be hit


@patch('app.routes.business_routes.redis_client', new_callable=MagicMock)
def test_get_navigation_profile_caches_not_found(mock_redis_client, test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    # Arrange
    slug = "non-existent-slug"
    cache_key = f"business_profile_nav_slug:{slug}"

    # First call: cache miss, DB miss, then cache "None"
    mock_redis_client.get.return_value = None
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first.return_value = None

    # Act (1st call)
    response1 = test_app_client_fixture.get(f"/business-profile/navigation-profile/slug/{slug}")

    # Assert (1st call)
    assert response1.status_code == 404
    mock_redis_client.get.assert_called_once_with(cache_key)
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first.assert_called_once()
    mock_redis_client.set.assert_called_once_with(cache_key, json.dumps(None), ex=300)

    # Arrange for 2nd call: simulate "None" is now cached
    mock_redis_client.get.reset_mock() # Reset call count for get
    mock_redis_client.set.reset_mock() # Reset call count for set
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first.reset_mock()
    mock_redis_client.get.return_value = json.dumps(None)

    # Act (2nd call)
    response2 = test_app_client_fixture.get(f"/business-profile/navigation-profile/slug/{slug}")

    # Assert (2nd call)
    assert response2.status_code == 404 # Should still be 404 due to cached "None"
    mock_redis_client.get.assert_called_once_with(cache_key) # Get was called
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first.assert_not_called() # DB not hit
    mock_redis_client.set.assert_not_called() # Set not called again


@patch('app.routes.business_routes.redis_client', new_callable=MagicMock)
def test_navigation_profile_cache_invalidation_on_update(mock_redis_client, test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    # Arrange: Setup an existing profile
    original_name = "Original Cache Biz"
    original_slug = slugify(original_name)
    profile_id = 22
    mock_profile_orm = create_mock_db_profile(id=profile_id, name=original_name, slug=original_slug)

    # Simulate that the profile to be updated exists in the DB
    # The update route uses filter(ANY).first() initially for the profile to update.
    # Then, if name changes, it uses another filter(ANY).first() to check for slug conflict.
    mock_db_session.query(BusinessProfileModel).filter(ANY).first.side_effect = [mock_profile_orm, None] # No slug conflict for new name

    updated_name = "Updated Cache Biz"
    updated_slug = slugify(updated_name)
    update_payload = {"business_name": updated_name, "industry": "E-commerce"}

    original_cache_key = f"business_profile_nav_slug:{original_slug}"
    updated_cache_key = f"business_profile_nav_slug:{updated_slug}"

    # Act: Update the business profile
    response = test_app_client_fixture.put(f"/business-profile/{profile_id}", json=update_payload)

    # Assert
    assert response.status_code == 200
    assert response.json()["slug"] == updated_slug # Slug should have been updated

    # Check cache invalidation calls
    # As per implementation, it deletes old_slug cache then new_slug cache
    mock_redis_client.delete.assert_any_call(original_cache_key)
    mock_redis_client.delete.assert_any_call(updated_cache_key)
    # Ensure delete was called for both (or at least twice if old_slug == new_slug, though logic handles that)
    assert mock_redis_client.delete.call_count >= 1 # At least one if slug didn't change, two if it did.
                                                    # Current logic calls delete on new_slug regardless.


@patch('app.routes.business_routes.redis_client', new_callable=MagicMock)
def test_get_navigation_profile_redis_connection_error(mock_redis_client, test_app_client_fixture: TestClient, mock_db_session: MagicMock):
    # Arrange
    slug = "redis-error-slug"
    mock_redis_client.get.side_effect = redis.exceptions.ConnectionError("Test Redis connection error")
    # If get fails, set should ideally not be called or handled gracefully by the route if it also fails.
    # For this test, primarily ensuring GET fallback.
    mock_redis_client.set = MagicMock()


    mock_profile_orm = create_mock_db_profile(id=23, name="Redis Error Fallback", slug=slug)
    mock_db_session.query(BusinessProfileModel).filter(BusinessProfileModel.slug == slug).first.return_value = mock_profile_orm

    # Act
    response = test_app_client_fixture.get(f"/business-profile/navigation-profile/slug/{slug}")

    # Assert
    assert response.status_code == 200 # Should fallback to DB
    assert response.json()["business_name"] == "Redis Error Fallback"
    mock_redis_client.get.assert_called_once_with(f"business_profile_nav_slug:{slug}")
    # Check if set was attempted despite connection error on get (depends on route's error handling for set)
    # The current route logic would attempt a set if DB query is successful, even if GET failed.
    # So, we expect set to be called, but it might also raise an error (which should be caught by the route).
    # For simplicity, let's assume set will also fail or we just check it was called.
    # If redis_client.set also throws ConnectionError, the route should still return data from DB.
    mock_redis_client.set.assert_called_once()
    # To be more precise, if redis_client.set also fails:
    # mock_redis_client.set.side_effect = redis.exceptions.ConnectionError("Test Redis connection error on set")
    # # ... then re-run and ensure the response is still 200 from DB. The current code logs the set error but proceeds.
