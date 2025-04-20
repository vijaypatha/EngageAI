import openai
import os
import json
from app.services.style_analyzer import get_style_guide

def generate_sms(
    business_type,
    customer_name,
    event,
    business_id,
    db,
    lifecycle_stage,
    pain_points,
    interaction_history,
    representative_name="Your Name",
    business_goal="build strong customer relationships",
):
    """Generate SMS matching the business owner's exact communication style."""
    
    # Get the business owner's comprehensive style guide
    style_guide = get_style_guide(business_id, db)
    
    # Format the style guide elements
    style_elements = {
        'phrases': '\n'.join(style_guide.get('key_phrases', [])),
        'patterns': '\n'.join(style_guide.get('message_patterns', [])),
        'personality': '\n'.join(style_guide.get('personality_traits', [])),
        'special': json.dumps(style_guide.get('special_elements', {}), indent=2),
        'style_notes': style_guide.get('style_notes', {})
    }

    prompt = f"""
IMPORTANT: Your reply must be under 80 characters. No long texts.

You are {representative_name}. Write a message about: "{event}"

YOUR EXACT VOICE & STYLE:

1. Your Common Phrases:
{style_elements['phrases']}

2. How You Structure Messages:
{style_elements['patterns']}

3. Your Personality:
{style_elements['personality']}

4. Your Special Elements:
{style_elements['special']}

5. Your Style Notes:
{json.dumps(style_elements['style_notes'], indent=2)}

Context:
- Customer: {customer_name}
- Stage: {lifecycle_stage}
- Pain Points: {pain_points}
- History: {interaction_history}
- Business Goal: {business_goal}

✍️ Guidelines:
- Keep under 160 characters
- Use 1-2 relevant emojis naturally
- End with "– {representative_name}, {business_name}"

CRITICAL RULES:
1. Write EXACTLY as if you are this person
2. Use their exact communication patterns
3. Include their specific types of phrases
4. Match their personality perfectly
5. Keep message under 80 characters
6. Make it impossible to tell this wasn't written by them

Write your message:
"""

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert at matching exact communication styles."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=60
    )

    final = response.choices[0].message.content.strip()
    return final if len(final) <= 80 else final[:77] + "..."
