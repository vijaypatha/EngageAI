import pytest
from datetime import datetime, date, timedelta, timezone, time
from app.services.ai_service import parse_customer_notes, parse_business_profile_for_campaigns
from unittest.mock import patch, MagicMock, ANY, AsyncMock
import json
import uuid
import openai

from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.services.ai_service import AIService
from app.models import Customer, BusinessProfile, RoadmapMessage, MessageStatusEnum, Message
from app.schemas import RoadmapGenerate, RoadmapResponse, RoadmapMessageResponse
from app.config import settings


# Test cases for parse_customer_notes
@pytest.mark.parametrize("notes, expected_birthday_month, expected_birthday_day, expected_days_until_approx, expected_holidays", [
    ("Birthday on August 31", 8, 31, None, None),
    ("bday is mar 1st", 3, 1, None, None),
    ("My birthday: 02/14", 2, 14, None, None),
    ("Her bday is 12/25.", 12, 25, None, None),
    ("Birthday: April 30", 4, 30, None, None),
    ("Customer's birthday is May 15th", 5, 15, None, None),
    ("Notes: customer bday is June 7.", 6, 7, None, None),
    ("bday on july 4", 7, 4, None, None),
    ("Birthday is on Sep 5.", 9, 5, None, None),
    ("Bday: Oct. 23", 10, 23, None, None),
    ("Birthday - Nov 11", 11, 11, None, None),
    ("Birthday is Feb 30th", 2, 30, "INVALID_DATE_NO_DAYS_CALC", None),
    ("No birthday info here.", None, None, None, None),
    ("", None, None, None, None),
    ("Likes birthdays a lot.", None, None, None, None),
    ("Birthday was last week.", None, None, None, None),
    ("Bday: 13/01", None, None, None, None),
    ("Loves Christmas and New Year's!", None, None, None, ["Christmas", "New Year"]),
    ("Excited for July 4th fireworks.", None, None, None, ["July 4th"]),
    ("Plans for Thanksgiving dinner.", None, None, None, ["Thanksgiving"]),
    ("Getting an Easter basket.", None, None, None, ["Easter"]),
    ("Valentine's Day special.", None, None, None, ["Valentine's Day"]),
    ("Christmas is their favorite, also likes valentine's day.", None, None, None, ["Christmas", "Valentine's Day"]),
    ("Birthday: Dec 25. Loves Christmas!", 12, 25, None, ["Christmas"]),
])
def test_parse_customer_notes_birthday_and_holidays(notes, expected_birthday_month, expected_birthday_day, expected_days_until_approx, expected_holidays):
    parsed_info = parse_customer_notes(notes)
    if expected_days_until_approx == "INVALID_DATE_NO_DAYS_CALC":
        assert parsed_info.get('birthday_month') == expected_birthday_month
        assert parsed_info.get('birthday_day') == expected_birthday_day
        assert 'birthday_details_raw' in parsed_info
        assert 'days_until_birthday' not in parsed_info
    elif expected_birthday_month and expected_birthday_day:
        assert parsed_info.get('birthday_month') == expected_birthday_month
        assert parsed_info.get('birthday_day') == expected_birthday_day
        assert 'days_until_birthday' in parsed_info
    else:
        assert 'birthday_month' not in parsed_info
        assert 'birthday_day' not in parsed_info
        assert 'days_until_birthday' not in parsed_info
    if expected_holidays:
        assert sorted(parsed_info.get('mentioned_holidays_or_events', [])) == sorted(expected_holidays)
    else:
        assert 'mentioned_holidays_or_events' not in parsed_info

@patch('app.services.ai_service.datetime', autospec=True)
def test_parse_customer_notes_days_until_birthday_calculation(mock_datetime_class):
    mock_utcnow_instance = MagicMock(spec=datetime)
    mock_utcnow_instance.date.return_value = date(2023, 8, 15)
    mock_datetime_class.utcnow.return_value = mock_utcnow_instance

    def side_effect_constructor(*args, **kwargs):
        if len(args) >= 3 and isinstance(args[0], int) and isinstance(args[1], int) and isinstance(args[2], int):
            return datetime(*args, **kwargs)
        return MagicMock()
    mock_datetime_class.side_effect = side_effect_constructor

    parsed_info_passed = parse_customer_notes("Birthday: March 10")
    assert parsed_info_passed['birthday_month'] == 3
    assert parsed_info_passed['birthday_day'] == 10
    assert parsed_info_passed['days_until_birthday'] == (date(2024, 3, 10) - date(2023, 8, 15)).days

    parsed_info_upcoming = parse_customer_notes("Birthday: August 20")
    assert parsed_info_upcoming['birthday_month'] == 8
    assert parsed_info_upcoming['birthday_day'] == 20
    assert parsed_info_upcoming['days_until_birthday'] == 5

    parsed_info_today = parse_customer_notes("Birthday: August 15")
    assert parsed_info_today['birthday_month'] == 8
    assert parsed_info_today['birthday_day'] == 15
    assert parsed_info_today['days_until_birthday'] == 0

    parsed_info_tomorrow = parse_customer_notes("Birthday: August 16")
    assert parsed_info_tomorrow['birthday_month'] == 8
    assert parsed_info_tomorrow['birthday_day'] == 16
    assert parsed_info_tomorrow['days_until_birthday'] == 1

# Tests for parse_business_profile_for_campaigns
@pytest.mark.parametrize("business_goal, primary_services, expected_has_sales_info, expected_discounts, expected_product_focus", [
    ("Increase sales", "Product A, Product B", True, [], []),
    ("Run a 20% off sale on Product A", "Product A, Product B, Service C", True, ["20% off"], ["product a product a"]),
    ("Offer 10-15% discount for new customers", "General services", True, ["10-15% discount"], []),
    ("Promote our new Service X", "Service X, Other services", True, [], []),
    ("Get more leads", "Consulting", False, [], []),
    ("End of year sale on all items. 50% off everything!", "Retail store", True, ["50% off"], ["all items"]),
    ("", "", False, [], []),
    ("Clearance sale on old stock", "Electronics", True, [], ["old stock electronics"]),
])
def test_parse_business_profile_for_campaigns(business_goal, primary_services, expected_has_sales_info, expected_discounts, expected_product_focus):
    campaign_info = parse_business_profile_for_campaigns(business_goal, primary_services)
    assert campaign_info.get("has_sales_info") == expected_has_sales_info
    assert sorted(campaign_info.get("discounts_mentioned", [])) == sorted(expected_discounts)
    if expected_product_focus:
        assert all(item in campaign_info.get("product_focus_for_sales", []) for item in expected_product_focus)
    else:
        assert not campaign_info.get("product_focus_for_sales")

# Fixture for AIService instance
@pytest.fixture
def ai_service(db: Session, mock_openai_client: MagicMock):
    original_api_key = settings.OPENAI_API_KEY
    if not original_api_key:
        settings.OPENAI_API_KEY = "test_key_not_used_due_to_mocking"
    service = AIService(db=db)
    if not original_api_key:
        settings.OPENAI_API_KEY = None
    return service

@pytest.fixture
def mock_openai_client():
    with patch('app.services.ai_service.openai.Client') as mock_client_constructor:
        mock_instance = MagicMock()
        mock_client_constructor.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_style_service():
    with patch('app.services.ai_service.StyleService') as mock_ss_constructor:
        mock_instance = MagicMock()
        mock_instance.get_style_guide = AsyncMock(return_value={"tone": "friendly", "formatting": "casual"})
        mock_ss_constructor.return_value = mock_instance
        yield mock_instance

@pytest.mark.asyncio
async def test_generate_roadmap_customer_not_found(ai_service: AIService, db: Session, mock_openai_client, mock_style_service):
    data = RoadmapGenerate(customer_id=9999, business_id=1)
    with pytest.raises(HTTPException) as exc_info:
        await ai_service.generate_roadmap(data)
    assert exc_info.value.status_code == 404
    assert "Customer 9999 not found" in exc_info.value.detail

@pytest.mark.asyncio
async def test_generate_roadmap_business_not_found(ai_service: AIService, db: Session, mock_openai_client, mock_style_service, mock_customer: Customer):
    data = RoadmapGenerate(customer_id=mock_customer.id, business_id=9998)
    with pytest.raises(HTTPException) as exc_info:
        await ai_service.generate_roadmap(data)
    assert exc_info.value.status_code == 404
    assert "Business 9998 not found" in exc_info.value.detail

@pytest.mark.asyncio
async def test_generate_roadmap_success_simple(ai_service: AIService, db: Session, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile):
    data = RoadmapGenerate(customer_id=mock_customer.id, business_id=mock_business.id)
    ai_response_messages = [
        {"days_from_today": 7, "sms_text": "Hello from AI! - Test Rep from Test Business", "purpose": "Initial Check-in"},
        {"days_from_today": 90, "sms_text": "Quarterly follow-up! - Test Rep from Test Business", "purpose": "Quarterly Check-in"}
    ]
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({"messages": ai_response_messages})))]
    )
    roadmap_response = await ai_service.generate_roadmap(data)
    assert roadmap_response.status == "success"
    assert roadmap_response.total_messages == 2
    assert len(roadmap_response.roadmap) == 2
    db_messages = db.query(RoadmapMessage).filter(RoadmapMessage.customer_id == mock_customer.id).all()
    assert len(db_messages) == 2
    assert db_messages[0].smsContent == "Hello from AI! - Test Rep from Test Business"
    assert db_messages[0].status == MessageStatusEnum.DRAFT.value
    assert db_messages[0].relevance == "Initial Check-in"
    assert db_messages[1].smsContent == "Quarterly follow-up! - Test Rep from Test Business"
    mock_openai_client.chat.completions.create.assert_called_once()
    mock_style_service.get_style_guide.assert_called_once_with(mock_business.id, db)

@pytest.mark.asyncio
async def test_generate_roadmap_openai_api_error(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile):
    data = RoadmapGenerate(customer_id=mock_customer.id, business_id=mock_business.id)
    mock_openai_client.chat.completions.create.side_effect = openai.APIError("Test API Error", request=None, body=None)

    with pytest.raises(HTTPException) as exc_info:
        await ai_service.generate_roadmap(data)
    assert exc_info.value.status_code == 503
    assert "AI service error: Test API Error" in exc_info.value.detail

@pytest.mark.asyncio
async def test_generate_roadmap_ai_invalid_json_response(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile):
    data = RoadmapGenerate(customer_id=mock_customer.id, business_id=mock_business.id)
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="This is not valid JSON"))]
    )

    with pytest.raises(HTTPException) as exc_info:
        await ai_service.generate_roadmap(data)
    assert exc_info.value.status_code == 400
    assert "AI invalid JSON" in exc_info.value.detail

@pytest.mark.asyncio
async def test_generate_roadmap_ai_missing_messages_key(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile):
    data = RoadmapGenerate(customer_id=mock_customer.id, business_id=mock_business.id)
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({"not_messages": []})))]
    )

    with pytest.raises(HTTPException) as exc_info:
        await ai_service.generate_roadmap(data)
    assert exc_info.value.status_code == 400
    assert "AI response missing 'messages' list" in exc_info.value.detail

@pytest.mark.asyncio
async def test_generate_roadmap_ai_messages_not_a_list(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile):
    data = RoadmapGenerate(customer_id=mock_customer.id, business_id=mock_business.id)
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({"messages": "not a list"})))]
    )

    with pytest.raises(HTTPException) as exc_info:
        await ai_service.generate_roadmap(data)
    assert exc_info.value.status_code == 400
    assert "AI response missing 'messages' list" in exc_info.value.detail

@pytest.mark.asyncio
async def test_generate_roadmap_ai_message_item_invalid_structure(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile, db: Session):
    data = RoadmapGenerate(customer_id=mock_customer.id, business_id=mock_business.id)
    ai_response_messages = [
        {"days_from_today": 7, "sms_text": "Valid message", "purpose": "Valid"},
        {"sms_text": "Missing days_from_today and purpose"},
        {"days_from_today": "not_an_int", "sms_text": "Invalid days type", "purpose": "Type error"}
    ]
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({"messages": ai_response_messages})))]
    )

    roadmap_response = await ai_service.generate_roadmap(data)

    assert roadmap_response.status == "success"
    assert roadmap_response.total_messages == 1
    assert len(roadmap_response.roadmap) == 1
    assert roadmap_response.roadmap[0].message == "Valid message"

    db_messages = db.query(RoadmapMessage).filter(RoadmapMessage.customer_id == mock_customer.id).all()
    assert len(db_messages) == 1
    assert db_messages[0].smsContent == "Valid message"

@pytest.mark.asyncio
async def test_generate_roadmap_birthday_scheduling(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile, db: Session):
    data = RoadmapGenerate(customer_id=mock_customer.id, business_id=mock_business.id)

    with patch('app.services.ai_service.parse_customer_notes', return_value={'birthday_month': 8, 'birthday_day': 25, 'days_until_birthday': 10}) as mock_parse_notes, \
         patch('app.services.ai_service.datetime', autospec=True) as mock_datetime_class:

        mock_utcnow_instance = MagicMock(spec=datetime)
        mock_utcnow_instance.date.return_value = date(2023, 8, 15)
        mock_utcnow_instance.strftime.return_value = "2023-08-15"
        mock_datetime_class.utcnow.return_value = mock_utcnow_instance

        def side_effect_datetime_constructor(*args, **kwargs):
            if len(args) >= 3 and isinstance(args[0], int) and isinstance(args[1], int) and isinstance(args[2], int):
                return datetime(*args, **kwargs)
            if len(args) == 2 and isinstance(args[0], date) and isinstance(args[1], time):
                return datetime.combine(*args, **kwargs)
            return MagicMock()

        mock_datetime_class.side_effect = side_effect_datetime_constructor
        mock_datetime_class.strptime = datetime.strptime
        mock_datetime_class.combine = datetime.combine
        mock_datetime_class.now.return_value = datetime(2023, 8, 15, 10, 0, 0, tzinfo=timezone.utc)

        ai_response_messages = [
            {"days_from_today": 10, "sms_text": "Happy Birthday! - Test Rep", "purpose": "Birthday Wish"},
            {"days_from_today": 90, "sms_text": "Quarterly check-in - Test Rep", "purpose": "Quarterly Check-in"}
        ]
        mock_openai_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps({"messages": ai_response_messages})))]
        )

        await ai_service.generate_roadmap(data)

        mock_parse_notes.assert_called_once()

        called_args, called_kwargs = mock_openai_client.chat.completions.create.call_args
        user_prompt_content = called_kwargs['messages'][1]['content']
        assert '"days_until_birthday": 10' in user_prompt_content
        assert '"birthday_month": 8' in user_prompt_content
        assert '"birthday_day": 25' in user_prompt_content

        db_messages = db.query(RoadmapMessage).filter(RoadmapMessage.customer_id == mock_customer.id).order_by(RoadmapMessage.send_datetime_utc).all()
        assert len(db_messages) == 2
        assert db_messages[0].smsContent == "Happy Birthday! - Test Rep"

        expected_send_date_birthday = datetime(2023, 8, 25, 10, 0, 0)
        assert db_messages[0].send_datetime_utc.replace(tzinfo=None) == expected_send_date_birthday

@pytest.mark.asyncio
async def test_generate_roadmap_holiday_scheduling_july4th(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile, db: Session):
    data = RoadmapGenerate(customer_id=mock_customer.id, business_id=mock_business.id)

    with patch('app.services.ai_service.datetime', autospec=True) as mock_datetime_class:
        mock_utcnow_instance = MagicMock(spec=datetime)
        mock_utcnow_instance.date.return_value = date(2023, 6, 15)
        mock_utcnow_instance.strftime.return_value = "2023-06-15"
        mock_datetime_class.utcnow.return_value = mock_utcnow_instance

        def side_effect_datetime_constructor(*args, **kwargs):
            if len(args) >= 3 and isinstance(args[0], int) and isinstance(args[1], int) and isinstance(args[2], int):
                return datetime(*args, **kwargs)
            if len(args) == 2 and isinstance(args[0], date) and isinstance(args[1], time):
                return datetime.combine(*args, **kwargs)
            return MagicMock()

        mock_datetime_class.side_effect = side_effect_datetime_constructor
        mock_datetime_class.strptime = datetime.strptime
        mock_datetime_class.combine = datetime.combine
        mock_datetime_class.now.return_value = datetime(2023, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

        ai_response_messages = [
            {"days_from_today": 18, "sms_text": "Getting ready for July 4th! - Test Rep", "purpose": "July 4th Pre-greeting"},
        ]
        mock_openai_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps({"messages": ai_response_messages})))]
        )

        await ai_service.generate_roadmap(data)

        db_messages = db.query(RoadmapMessage).filter(RoadmapMessage.customer_id == mock_customer.id).all()
        assert len(db_messages) == 1
        assert "July 4th" in db_messages[0].relevance

        expected_send_date_july4th = datetime(2023, 7, 3, 10, 0, 0)
        assert db_messages[0].send_datetime_utc.replace(tzinfo=None) == expected_send_date_july4th

@pytest.mark.asyncio
async def test_generate_sms_response_success(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile):
    incoming_message = "Hello, I have a question."
    mock_customer.interaction_history = "Previous chat."
    mock_business.enable_ai_faq_auto_reply = False

    expected_ai_reply_text = "This is a helpful AI reply. - Test Rep"
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=expected_ai_reply_text))]
    )
    mock_style_service.get_style_guide.return_value = {"tone": "professional"}

    response_dict = await ai_service.generate_sms_response(
        message=incoming_message,
        customer_id=mock_customer.id,
        business_id=mock_business.id
    )

    assert response_dict["text"] == expected_ai_reply_text
    assert response_dict["is_faq_answer"] is False
    mock_openai_client.chat.completions.create.assert_called_once()
    call_args, called_kwargs = mock_openai_client.chat.completions.create.call_args
    user_prompt = called_kwargs['messages'][1]['content']
    assert incoming_message in user_prompt
    assert mock_customer.customer_name in user_prompt
    assert "professional" in user_prompt

@pytest.mark.asyncio
async def test_generate_sms_response_customer_not_found(ai_service: AIService, mock_openai_client, mock_style_service):
    with pytest.raises(HTTPException) as exc_info:
        await ai_service.generate_sms_response(message="test", customer_id=999, business_id=1)
    assert exc_info.value.status_code == 404
    assert "Customer not found" in exc_info.value.detail

@pytest.mark.asyncio
async def test_generate_sms_response_business_not_found(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer):
    with pytest.raises(HTTPException) as exc_info:
        await ai_service.generate_sms_response(message="test", customer_id=mock_customer.id, business_id=998)
    assert exc_info.value.status_code == 404
    assert "Business not found" in exc_info.value.detail

@pytest.mark.asyncio
async def test_generate_sms_response_faq_triggered(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile):
    incoming_message = "What is your address?"
    mock_business.enable_ai_faq_auto_reply = True
    mock_business.structured_faq_data = {"address": "123 Main St"}

    ai_reply_with_marker = "Our address is 123 Main St. ##FAQ_ANSWERED_FOR_DIRECT_REPLY## - Test Rep"
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=ai_reply_with_marker))]
    )

    response_dict = await ai_service.generate_sms_response(
        message=incoming_message, customer_id=mock_customer.id, business_id=mock_business.id
    )

    assert response_dict["text"] == "Our address is 123 Main St. - Test Rep"
    assert response_dict["is_faq_answer"] is True

    call_args, called_kwargs = mock_openai_client.chat.completions.create.call_args
    user_prompt = called_kwargs['messages'][1]['content']
    assert "Address: 123 Main St" in user_prompt
    assert "##FAQ_ANSWERED_FOR_DIRECT_REPLY##" in user_prompt

@pytest.mark.asyncio
async def test_generate_sms_response_faq_general_context(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile):
    incoming_message = "Tell me about your services."
    mock_business.enable_ai_faq_auto_reply = True
    mock_business.structured_faq_data = {"address": "123 Main St", "custom_faqs": [{"question": "Q1", "answer": "A1"}]}

    ai_reply_general = "We offer great services! - Test Rep"
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=ai_reply_general))]
    )

    response_dict = await ai_service.generate_sms_response(
        message=incoming_message, customer_id=mock_customer.id, business_id=mock_business.id
    )

    assert response_dict["text"] == ai_reply_general
    assert response_dict["is_faq_answer"] is False

    call_args, called_kwargs = mock_openai_client.chat.completions.create.call_args
    user_prompt = called_kwargs['messages'][1]['content']
    assert "- Business address: 123 Main St" in user_prompt # Corrected assertion
    assert "Q: Q1 -> A: A1" in user_prompt

@pytest.mark.asyncio
async def test_generate_sms_response_openai_error(ai_service: AIService, mock_openai_client, mock_style_service, mock_customer: Customer, mock_business: BusinessProfile):
    mock_openai_client.chat.completions.create.side_effect = openai.APIError("Test API Error", request=None, body=None)
    with pytest.raises(openai.APIError):
         await ai_service.generate_sms_response(
            message="A question", customer_id=mock_customer.id, business_id=mock_business.id
        )

# Placeholder for generate_sms_response tests - to be expanded later
@pytest.mark.asyncio
async def test_generate_sms_response_basic(ai_service: AIService, mock_openai_client):
    # This test was removed as it's covered by the more detailed tests above.
    pass
