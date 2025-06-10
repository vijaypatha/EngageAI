import pytest
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import json
from fastapi import HTTPException, status # status might be needed for assertions

from app.models import (
    CoPilotNudge,
    Customer,
    TargetedEvent,
    NudgeTypeEnum,
    NudgeStatusEnum,
    BusinessProfile,
    RoadmapMessage,
    MessageStatusEnum # Ensure this is imported
)
from app.services.copilot_growth_opportunity_service import CoPilotGrowthOpportunityService
from app.schemas import CoPilotNudgeCreate # If used directly, else not needed for service tests

# Assuming conftest.py provides:
# - db: Session fixture
# - mock_business: BusinessProfile ORM instance fixture
# - mock_customer: Customer ORM instance fixture (we might need more customers)

@pytest.fixture
def growth_service(db: Session):
    return CoPilotGrowthOpportunityService(db=db)

@pytest.fixture
def customer1(db: Session, mock_business: BusinessProfile):
    cust = Customer(business_id=mock_business.id, customer_name="Customer One", phone="+15550000001", opted_in=True)
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return cust

@pytest.fixture
def customer2(db: Session, mock_business: BusinessProfile):
    cust = Customer(business_id=mock_business.id, customer_name="Customer Two", phone="+15550000002", opted_in=True)
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return cust

@pytest.fixture
def customer3(db: Session, mock_business: BusinessProfile):
    cust = Customer(business_id=mock_business.id, customer_name="Customer Three", phone="+15550000003", opted_in=True)
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return cust

# Helper to create a CoPilotNudge
def create_nudge(db: Session, business_id: int, customer_id: int = None,
                 nudge_type: NudgeTypeEnum = NudgeTypeEnum.SENTIMENT_POSITIVE,
                 status: NudgeStatusEnum = NudgeStatusEnum.ACTIVE,
                 created_at: datetime = None,
                 payload: Dict[str, Any] = None):
    if created_at is None:
        created_at = datetime.utcnow()

    nudge = CoPilotNudge(
        business_id=business_id,
        customer_id=customer_id,
        nudge_type=nudge_type,
        status=status,
        message_snippet="Test snippet",
        ai_suggestion="Test suggestion",
        ai_suggestion_payload=payload,
        created_at=created_at,
        updated_at=created_at
    )
    db.add(nudge)
    db.commit()
    db.refresh(nudge)
    return nudge

# Helper to create a TargetedEvent
def create_event(db: Session, business_id: int, customer_id: int,
                 status: str = 'Completed',
                 event_datetime_utc: datetime = None):
    if event_datetime_utc is None:
        event_datetime_utc = datetime.utcnow()

    event = TargetedEvent(
        business_id=business_id,
        customer_id=customer_id,
        purpose="Test Event",
        event_datetime_utc=event_datetime_utc,
        status=status,
        # Add other required fields for TargetedEvent if any
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event

# Tests for identify_referral_opportunities
def test_identify_referral_opportunities_no_qualifying_customers(growth_service: CoPilotGrowthOpportunityService, mock_business: BusinessProfile):
    # Arrange: No positive nudges, no completed events

    # Act
    nudges = growth_service.identify_referral_opportunities(mock_business.id)

    # Assert
    assert len(nudges) == 0


@pytest.mark.asyncio
async def test_launch_growth_campaign_success(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile, customer1: Customer, customer2: Customer
):
    # Arrange
    campaign_payload = {
        "opportunity_type": "REFERRAL_CAMPAIGN", # Could be any type the method handles
        "customer_ids": [customer1.id, customer2.id],
        "draft_message": "Hi {customer_name}, special offer for you!"
    }
    nudge = create_nudge(
        db, mock_business.id,
        nudge_type=NudgeTypeEnum.GOAL_OPPORTUNITY,
        status=NudgeStatusEnum.ACTIVE,
        payload=campaign_payload
    )

    # Act
    result = await growth_service.launch_growth_campaign_from_nudge(nudge.id, mock_business.id)

    # Assert
    assert result["drafts_created"] == 2
    assert "drafts created successfully" in result["message"]

    db.refresh(nudge)
    assert nudge.status == NudgeStatusEnum.ACTIONED

    drafts = db.query(RoadmapMessage).filter(
        RoadmapMessage.business_id == mock_business.id,
        RoadmapMessage.customer_id.in_([customer1.id, customer2.id])
    ).all()
    assert len(drafts) == 2
    for draft in drafts:
        assert draft.status == MessageStatusEnum.PENDING_REVIEW.value
        if draft.customer_id == customer1.id:
            assert "Customer One" in draft.smsContent
        elif draft.customer_id == customer2.id:
            assert "Customer Two" in draft.smsContent
        assert "special offer for you!" in draft.smsContent

@pytest.mark.asyncio
async def test_launch_growth_campaign_nudge_not_found(growth_service: CoPilotGrowthOpportunityService, mock_business: BusinessProfile):
    with pytest.raises(HTTPException) as exc_info:
        await growth_service.launch_growth_campaign_from_nudge(9999, mock_business.id)
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert "Nudge not found" in exc_info.value.detail

@pytest.mark.asyncio
async def test_launch_growth_campaign_nudge_not_active(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile
):
    nudge = create_nudge(db, mock_business.id, nudge_type=NudgeTypeEnum.GOAL_OPPORTUNITY, status=NudgeStatusEnum.ACTIONED)
    with pytest.raises(HTTPException) as exc_info:
        await growth_service.launch_growth_campaign_from_nudge(nudge.id, mock_business.id)
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Nudge is not active" in exc_info.value.detail

@pytest.mark.asyncio
async def test_launch_growth_campaign_nudge_wrong_type(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile
):
    nudge = create_nudge(db, mock_business.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, status=NudgeStatusEnum.ACTIVE)
    with pytest.raises(HTTPException) as exc_info:
        await growth_service.launch_growth_campaign_from_nudge(nudge.id, mock_business.id)
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "only for goal opportunity nudges" in exc_info.value.detail

@pytest.mark.asyncio
async def test_launch_growth_campaign_nudge_payload_incomplete(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile
):
    # Missing customer_ids
    nudge1 = create_nudge(db, mock_business.id, nudge_type=NudgeTypeEnum.GOAL_OPPORTUNITY, status=NudgeStatusEnum.ACTIVE, payload={"draft_message": "Hello"})
    with pytest.raises(HTTPException) as exc_info1:
        await growth_service.launch_growth_campaign_from_nudge(nudge1.id, mock_business.id)
    assert exc_info1.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Nudge data is incomplete" in exc_info1.value.detail

    # Missing draft_message
    nudge2 = create_nudge(db, mock_business.id, nudge_type=NudgeTypeEnum.GOAL_OPPORTUNITY, status=NudgeStatusEnum.ACTIVE, payload={"customer_ids": [1]})
    with pytest.raises(HTTPException) as exc_info2:
        await growth_service.launch_growth_campaign_from_nudge(nudge2.id, mock_business.id)
    assert exc_info2.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Nudge data is incomplete" in exc_info2.value.detail


@pytest.mark.asyncio # Method is not async, but test might use async fixtures if any were added later
def test_identify_re_engagement_no_qualifying_customers(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile, customer1: Customer
):
    # Arrange
    # Customer1: < 2 completed events
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=100))
    # Customer1: has recent nudge (activity)
    create_nudge(db, mock_business.id, customer1.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=30))

    # Act
    nudges = growth_service.identify_re_engagement_opportunities(mock_business.id)

    # Assert
    assert len(nudges) == 0

@pytest.mark.asyncio
def test_identify_re_engagement_qualifying_customer_found(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile, customer1: Customer, customer2: Customer
):
    # Arrange
    # Customer1: 2 completed events, no recent nudges
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=100))
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=120))
    # Ensure no recent nudges for customer1 (older one is fine)
    create_nudge(db, mock_business.id, customer1.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=100))


    # Customer2: 2 completed events, but has a recent nudge
    create_event(db, mock_business.id, customer2.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=100))
    create_event(db, mock_business.id, customer2.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=120))
    create_nudge(db, mock_business.id, customer2.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=30)) # Recent activity

    # Act
    nudges = growth_service.identify_re_engagement_opportunities(mock_business.id)

    # Assert
    assert len(nudges) == 1
    nudge = nudges[0]
    assert nudge.business_id == mock_business.id
    assert nudge.nudge_type == NudgeTypeEnum.GOAL_OPPORTUNITY
    assert nudge.status == NudgeStatusEnum.ACTIVE
    assert nudge.ai_suggestion_payload.get("opportunity_type") == "RE_ENGAGEMENT_CAMPAIGN"
    assert customer1.id in nudge.ai_suggestion_payload.get("customer_ids", [])
    assert customer2.id not in nudge.ai_suggestion_payload.get("customer_ids", [])
    assert "1 previously high-value customer" in nudge.message_snippet
    assert "have been inactive for over 90 days" in nudge.message_snippet

@pytest.mark.asyncio
def test_identify_re_engagement_customer_already_in_recent_re_engagement_nudge(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile, customer1: Customer
):
    # Arrange
    # Customer1: Qualifies otherwise
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=100))
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=120))
    create_nudge(db, mock_business.id, customer1.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=95))


    # Existing recent RE_ENGAGEMENT_CAMPAIGN nudge for customer1
    create_nudge(
        db, mock_business.id,
        nudge_type=NudgeTypeEnum.GOAL_OPPORTUNITY,
        status=NudgeStatusEnum.ACTIVE,
        created_at=datetime.utcnow() - timedelta(days=15), # Recent
        payload={"opportunity_type": "RE_ENGAGEMENT_CAMPAIGN", "customer_ids": [customer1.id]}
    )

    # Act
    nudges = growth_service.identify_re_engagement_opportunities(mock_business.id)

    # Assert
    assert len(nudges) == 0

@pytest.mark.asyncio
def test_identify_re_engagement_date_boundaries(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile, customer1: Customer, customer2: Customer
):
    # Customer 1: Nudge just inside 90-day inactivity window (should NOT be considered inactive)
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=100))
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=120))
    create_nudge(db, mock_business.id, customer1.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=89))

    # Customer 2: Nudge just outside 90-day inactivity window (SHOULD be considered inactive)
    create_event(db, mock_business.id, customer2.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=100))
    create_event(db, mock_business.id, customer2.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=120))
    create_nudge(db, mock_business.id, customer2.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=91))

    nudges = growth_service.identify_re_engagement_opportunities(mock_business.id)
    assert len(nudges) == 1, "Only customer2 with nudge >90 days ago should qualify"
    assert customer2.id in nudges[0].ai_suggestion_payload.get("customer_ids", [])
    assert customer1.id not in nudges[0].ai_suggestion_payload.get("customer_ids", [])


def test_identify_referral_opportunities_multiple_qualifying_customers(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile, customer1: Customer, customer2: Customer, customer3: Customer
):
    # Arrange
    # Customer1: happy and serviced
    create_nudge(db, mock_business.id, customer1.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=10))
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=20))

    # Customer2: also happy and serviced
    create_nudge(db, mock_business.id, customer2.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=12))
    create_event(db, mock_business.id, customer2.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=22))

    # Customer3: only serviced, not happy based on nudge
    create_event(db, mock_business.id, customer3.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=25))

    # Act
    nudges = growth_service.identify_referral_opportunities(mock_business.id)

    # Assert
    assert len(nudges) == 1
    nudge = nudges[0]
    assert nudge.nudge_type == NudgeTypeEnum.GOAL_OPPORTUNITY
    payload_customer_ids = sorted(nudge.ai_suggestion_payload.get("customer_ids", []))
    assert payload_customer_ids == sorted([customer1.id, customer2.id])
    assert str(customer3.id) not in payload_customer_ids # Ensure customer3 is not included
    assert "You have 2 happy customers who recently completed their service." in nudge.message_snippet


def test_identify_referral_opportunities_date_boundaries(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile, customer1: Customer
):
    # Arrange
    # Nudge just outside 30 days (should not qualify)
    create_nudge(db, mock_business.id, customer1.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=31))
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=20))

    nudges = growth_service.identify_referral_opportunities(mock_business.id)
    assert len(nudges) == 0, "Customer with positive nudge >30 days ago should not qualify"

    # Reset (clear previous) and test event boundary
    db.query(CoPilotNudge).delete()
    db.query(TargetedEvent).delete()
    db.commit()

    create_nudge(db, mock_business.id, customer1.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=10))
    # Event just outside 60 days (should not qualify)
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=61))

    nudges = growth_service.identify_referral_opportunities(mock_business.id)
    assert len(nudges) == 0, "Customer with event >60 days ago should not qualify"

    # Reset and test both conditions met just within boundary
    db.query(CoPilotNudge).delete()
    db.query(TargetedEvent).delete()
    db.commit()

    create_nudge(db, mock_business.id, customer1.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=29))
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=59))

    nudges = growth_service.identify_referral_opportunities(mock_business.id)
    assert len(nudges) == 1, "Customer meeting exact boundary conditions should qualify"


def test_identify_referral_opportunities_qualifies_if_old_referral_nudge(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile, customer1: Customer
):
    # Arrange
    # Customer1: happy and serviced
    create_nudge(db, mock_business.id, customer1.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=10))
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=20))

    # Existing OLD referral nudge for customer1 (should not prevent new one)
    create_nudge(
        db, mock_business.id,
        nudge_type=NudgeTypeEnum.GOAL_OPPORTUNITY,
        status=NudgeStatusEnum.ACTIONED, # or ACTIVE, but old
        created_at=datetime.utcnow() - timedelta(days=35), # Older than 30 days
        payload={"opportunity_type": "REFERRAL_CAMPAIGN", "customer_ids": [customer1.id]}
    )

    # Act
    nudges = growth_service.identify_referral_opportunities(mock_business.id)

    # Assert
    assert len(nudges) == 1
    assert customer1.id in nudges[0].ai_suggestion_payload.get("customer_ids", [])

def test_identify_referral_opportunities_one_qualifying_customer(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile, customer1: Customer, customer2: Customer
):
    # Arrange
    # Customer1: happy and serviced
    create_nudge(db, mock_business.id, customer1.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=10))
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=20))

    # Customer2: only happy
    create_nudge(db, mock_business.id, customer2.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=5))

    # Act
    nudges = growth_service.identify_referral_opportunities(mock_business.id)

    # Assert
    assert len(nudges) == 1
    nudge = nudges[0]
    assert nudge.business_id == mock_business.id
    assert nudge.nudge_type == NudgeTypeEnum.GOAL_OPPORTUNITY
    assert nudge.status == NudgeStatusEnum.ACTIVE
    assert nudge.ai_suggestion_payload.get("opportunity_type") == "REFERRAL_CAMPAIGN"
    assert customer1.id in nudge.ai_suggestion_payload.get("customer_ids", [])
    assert customer2.id not in nudge.ai_suggestion_payload.get("customer_ids", [])
    assert "You have 1 happy customer who recently completed their service." in nudge.message_snippet

def test_identify_referral_opportunities_customer_already_in_recent_nudge(
    growth_service: CoPilotGrowthOpportunityService, db: Session, mock_business: BusinessProfile, customer1: Customer
):
    # Arrange
    # Customer1: happy and serviced
    create_nudge(db, mock_business.id, customer1.id, nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE, created_at=datetime.utcnow() - timedelta(days=10))
    create_event(db, mock_business.id, customer1.id, status='Completed', event_datetime_utc=datetime.utcnow() - timedelta(days=20))

    # Existing recent referral nudge for customer1
    create_nudge(
        db, mock_business.id, customer_id=None, # Campaign nudges might not have a single customer_id
        nudge_type=NudgeTypeEnum.GOAL_OPPORTUNITY,
        status=NudgeStatusEnum.ACTIVE,
        created_at=datetime.utcnow() - timedelta(days=5),
        payload={"opportunity_type": "REFERRAL_CAMPAIGN", "customer_ids": [customer1.id]}
    )

    # Act
    nudges = growth_service.identify_referral_opportunities(mock_business.id)

    # Assert
    assert len(nudges) == 0
