import openai
import os
import json
from datetime import datetime, timedelta
import logging
from app.services.style_analyzer import get_style_guide

logger = logging.getLogger(__name__)

def extract_special_dates(customer_info: str) -> dict:
    """Extract special dates from customer information."""
    import re
    
    special_dates = {}
    info_lower = customer_info.lower()
    
    # Extract birthday
    birthday_patterns = [
        r'birthday\s+(?:is\s+)?(?:on\s+)?([a-z]+)\s+(\d+)(?:st|nd|rd|th)?',
        r'birthday:?\s+([a-z]+)\s+(\d+)(?:st|nd|rd|th)?'
    ]
    
    for pattern in birthday_patterns:
        match = re.search(pattern, info_lower)
        if match:
            month_name, day = match.groups()
            month_num = {
                'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
                'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
                'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'october': 10, 'oct': 10,
                'november': 11, 'nov': 11, 'december': 12, 'dec': 12
            }.get(month_name.lower())
            
            if month_num:
                special_dates['birthday'] = {
                    'month': month_num,
                    'day': int(day),
                    'importance': 'high'
                }
    
    # Extract holidays
    holidays = {
        'july 4th': {'month': 7, 'day': 4},
        'thanksgiving': {'month': 11, 'day': lambda y: get_thanksgiving_day(y)},
        'christmas': {'month': 12, 'day': 25},
        'new year': {'month': 1, 'day': 1}
    }
    
    for holiday, date_info in holidays.items():
        if holiday in info_lower:
            importance = 'high' if f'loves {holiday}' in info_lower else 'medium'
            special_dates[holiday] = {
                'month': date_info['month'],
                'day': date_info['day'] if isinstance(date_info['day'], int) else date_info['day'](datetime.now().year),
                'importance': importance
            }
    
    return special_dates

def get_thanksgiving_day(year):
    """Calculate Thanksgiving day for a given year."""
    import calendar
    c = calendar.monthcalendar(year, 11)
    return [day for day in [week[calendar.THURSDAY] for week in c] if day != 0][3]

def calculate_days_until(special_dates):
    """Calculate days until each special date."""
    today = datetime.now()
    date_offsets = {}
    
    for event, info in special_dates.items():
        target_date = datetime(today.year, info['month'], info['day'])
        if target_date < today:
            target_date = datetime(today.year + 1, info['month'], info['day'])
        
        days_until = (target_date - today).days
        date_offsets[event] = {
            'days_until': days_until,
            'importance': info['importance']
        }
    
    return date_offsets

def generate_sms_roadmap(
    business_type,
    customer_name,
    lifecycle_stage,
    pain_points,
    interaction_history,
    business_id,
    db,
    representative_name=None,
    business_name=None,
    business_goal="build strong customer relationships",
    primary_services="general services",
):
    """Generate SMS roadmap with proper timing and matching business owner's exact style."""
    
    # Get the business owner's comprehensive style guide
    style_guide = get_style_guide(business_id, db)
    
    # Extract dates and calculate offsets
    all_customer_info = f"{lifecycle_stage} {pain_points} {interaction_history}"
    special_dates = extract_special_dates(all_customer_info)
    date_offsets = calculate_days_until(special_dates)
    
    # Sort dates by proximity
    sorted_dates = sorted(
        date_offsets.items(),
        key=lambda x: (x[1]['importance'] != 'high', x[1]['days_until'])
    )
    
    # Format dates for prompt
    special_dates_text = "\n".join([
        f"   - {event.title()}: in {info['days_until']} days (Importance: {info['importance']})"
        for event, info in sorted_dates
    ])

    # Format the style guide elements
    style_elements = {
        'phrases': '\n'.join(style_guide.get('key_phrases', [])),
        'patterns': '\n'.join(style_guide.get('message_patterns', [])),
        'personality': '\n'.join(style_guide.get('personality_traits', [])),
        'special': json.dumps(style_guide.get('special_elements', {}), indent=2),
        'style_notes': style_guide.get('style_notes', {})
    }

    prompt = f"""
You are writing **4 SMS messages** as {representative_name} from {business_name}.
You MUST perfectly match their unique communication style.

YOUR EXACT VOICE & STYLE:
1. Phrases You Use:
{style_elements['phrases']}

2. How You Structure Messages:
{style_elements['patterns']}

3. Your Personality Traits:
{style_elements['personality']}

4. Your Special Elements (references, characters, etc):
{style_elements['special']}

5. Your Style Notes:
{json.dumps(style_elements['style_notes'], indent=2)}

✍️ Guidelines:
- Keep under 160 characters
- Use 1-2 relevant emojis naturally
- End with "– {representative_name}, {business_name}"

⚠️ CRITICAL TIMING REQUIREMENTS:
1. Use EXACT "Day X, HH:MM AM/PM" format for smsTiming
2. Important dates for this customer:
{special_dates_text}

3. Message Sequence MUST be:
   - Message 1: Day 0 (Initial consultation follow-up)
   - Messages 2-4: Schedule around special dates above
   
📅 Timing Rules:
- First message MUST be "Day 0, 10:00 AM"
- Special date messages should be 2 days before the event
- All times between 9:00 AM and 5:00 PM
- Monthly spacing between messages when no special dates

👤 Customer Context:
- Name: {customer_name}
- Status: {lifecycle_stage}
- Pain Points: {pain_points}
- Interaction History: {interaction_history}

CRITICAL RULES:
1. Write EXACTLY as if you are this person - match their voice perfectly
2. Use their exact communication patterns
3. Include their specific types of phrases and references
4. Keep their personality consistent across all messages
5. Each message must be under 160 characters
6. Don't miss the basics:
    - Greetings
    - Closing
    - Signoff
    - Wishes on holidays and birthdays

Return ONLY a JSON array of 4 messages with this structure:
{{
    "SMS Number": 1,
    "smsContent": "Message text...",
    "smsTiming": "Day X, HH:MM AM/PM",
    "dayOffset": X,
    "relevance": "Why this timing...",
    "successIndicator": "Expected response...",
    "whatif_customer_does_not_respond": "Next steps..."
}}
"""

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    logger.info(f"Generating roadmap for customer {customer_name} using business style guide")
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert at matching exact communication styles."},
            {"role": "user", "content": prompt}
        ]
    )
    
    return response.choices[0].message.content.strip()
