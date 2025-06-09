import pytest
from datetime import datetime, timezone
from app.models import Message, Engagement, Customer, BusinessProfile, Conversation
from app.services.stats_service import calculate_stats, calculate_reply_stats
from unittest.mock import patch
from sqlalchemy.orm import Session
import uuid

# Mock the celery tasks to avoid circular imports
@pytest.fixture(autouse=True)
def mock_celery_tasks():
    with patch('app.celery_tasks.process_scheduled_message_task') as mock_task: # Corrected patch path
        yield mock_task

@pytest.fixture
def test_data(db: Session, request):
    # Create test business with unique slug based on test name
    test_name = request.node.name
    business = BusinessProfile(
        business_name=f"Test Business {test_name}",
        slug=f"test-business-{test_name}"
    )
    db.add(business)
    db.flush()

    # Create test customer
    customer = Customer(
        business_id=business.id,
        customer_name="Test Customer",
        phone="+1234567890"
    )
    db.add(customer)
    db.flush()

    # Create test conversation
    conversation = Conversation(
        id=uuid.uuid4(),
        customer_id=customer.id,
        business_id=business.id,
        status="active"
    )
    db.add(conversation)
    db.flush()

    return {
        "business": business,
        "customer": customer,
        "conversation": conversation
    }

def test_sent_message_counting(db: Session, test_data):
    """Test that sent messages are counted correctly"""
    # Create messages with different combinations of status and sent_at
    messages = [
        # Case 1: status=sent, sent_at=None (should not count as sent)
        Message(
            conversation_id=test_data["conversation"].id,
            business_id=test_data["business"].id,
            customer_id=test_data["customer"].id,
            content="Test 1",
            message_type="scheduled",
            status="sent",
            sent_at=None,
            is_hidden=False
        ),
        # Case 2: status=scheduled, sent_at=set (should count as sent)
        Message(
            conversation_id=test_data["conversation"].id,
            business_id=test_data["business"].id,
            customer_id=test_data["customer"].id,
            content="Test 2",
            message_type="scheduled",
            status="scheduled",
            sent_at=datetime.now(timezone.utc),
            is_hidden=False
        ),
        # Case 3: Hidden message with sent_at (should not count)
        Message(
            conversation_id=test_data["conversation"].id,
            business_id=test_data["business"].id,
            customer_id=test_data["customer"].id,
            content="Test 3",
            message_type="scheduled",
            status="sent",
            sent_at=datetime.now(timezone.utc),
            is_hidden=True
        )
    ]
    
    for msg in messages:
        db.add(msg)
    db.commit()

    # Get stats
    stats = calculate_stats(test_data["business"].id, db)
    
    # Should only count Case 2 (sent_at set and not hidden)
    assert stats["sent"] == 1

def test_engagement_counting(db: Session, test_data):
    """Test that engagements are counted correctly"""
    # Create a message for the engagement
    message = Message(
        conversation_id=test_data["conversation"].id,
        business_id=test_data["business"].id,
        customer_id=test_data["customer"].id,
        content="Parent Message",
        message_type="scheduled",
        status="sent",
        sent_at=datetime.now(timezone.utc)
    )
    db.add(message)
    db.flush()

    # Create engagements
    engagements = [
        # Case 1: Regular sent engagement
        Engagement(
            message_id=message.id,
            business_id=test_data["business"].id,
            customer_id=test_data["customer"].id,
            response="Reply 1",
            ai_response="AI Response 1",
            status="sent",
            sent_at=datetime.now(timezone.utc)
        ),
        # Case 2: Pending engagement (should not count as sent)
        Engagement(
            message_id=message.id,
            business_id=test_data["business"].id,
            customer_id=test_data["customer"].id,
            response="Reply 2",
            ai_response="AI Response 2",
            status="pending_review",
            sent_at=None
        )
    ]

    for eng in engagements:
        db.add(eng)
    db.commit()

    # Get stats
    stats = calculate_stats(test_data["business"].id, db)
    reply_stats = calculate_reply_stats(test_data["business"].id, db)

    # Verify engagement counts
    assert stats["sent"] == 2  # 1 message + 1 sent engagement
    assert reply_stats["total_replies"] == 2  # Both engagements have responses
    assert reply_stats["total_sent"] == 2  # 1 message + 1 sent engagement

def test_reply_rate_calculation(db: Session, test_data):
    """Test that reply rate is calculated correctly"""
    # Create 4 sent messages
    messages = []
    for i in range(4):
        msg = Message(
            conversation_id=test_data["conversation"].id,
            business_id=test_data["business"].id,
            customer_id=test_data["customer"].id,
            content=f"Message {i}",
            message_type="scheduled",
            status="sent",
            sent_at=datetime.now(timezone.utc)
        )
        messages.append(msg)
        db.add(msg)
    db.flush()

    # Create 2 replies (50% reply rate)
    for i in range(2):
        eng = Engagement(
            message_id=messages[i].id,
            business_id=test_data["business"].id,
            customer_id=test_data["customer"].id,
            response=f"Reply {i}",
            status="sent"
        )
        db.add(eng)
    db.commit()

    # Get reply stats
    reply_stats = calculate_reply_stats(test_data["business"].id, db)
    
    # Verify reply rate
    assert reply_stats["total_sent"] == 4
    assert reply_stats["total_replies"] == 2
    assert reply_stats["reply_rate"] == 50.0  # 2/4 * 100 