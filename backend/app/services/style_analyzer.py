import openai
import os
import json
from datetime import datetime
from typing import List, Dict
from sqlalchemy.orm import Session
from app.models import BusinessOwnerStyle, BusinessProfile

def analyze_owner_style(responses: List[Dict[str, str]], business_id: int, db: Session) -> dict:
    """
    Analyze a set of business owner responses to create a comprehensive style guide.
    
    Args:
        responses: List of dict with 'scenario' and 'response' keys
        business_id: ID of the business
        db: Database session
    """
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Format responses for analysis
    formatted_examples = "\n\n".join([
        f"Customer: {r['scenario']}\nOwner: {r['response']}" 
        for r in responses
    ])
    
    prompt = f"""
    Analyze these business owner responses to create a detailed style guide:

    {formatted_examples}

    Create a comprehensive analysis that captures this owner's unique voice.
    Focus on patterns that make their communication style unique and authentic.

    Return a JSON object with these keys:
    1. key_phrases: Array of unique phrases or words they commonly use
    2. personality_traits: Array of distinct personality characteristics shown in their writing
    3. message_patterns: Array of patterns in how they structure responses
    4. special_elements: Object containing unique elements like:
       - recurring_characters: People they mention
       - metaphors: Types of comparisons they make
       - industry_specific: Industry terms they use uniquely
    5. style_notes: Object containing:
       - tone_characteristics: How they maintain their voice
       - situation_handling: How they approach different scenarios
       - authenticity_markers: What makes their voice genuine

    Focus on capturing what makes their voice UNIQUELY theirs.
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert in analyzing communication styles and patterns."},
            {"role": "user", "content": prompt}
        ]
    )
    
    analysis = json.loads(response.choices[0].message.content)
    
    # Update or create style guide in database
    style_guide = db.query(BusinessOwnerStyle).filter(
        BusinessOwnerStyle.business_id == business_id
    ).first()
    
    if not style_guide:
        style_guide = BusinessOwnerStyle(business_id=business_id)
        db.add(style_guide)
    
    # Update style guide with new analysis
    style_guide.key_phrases = json.dumps(analysis['key_phrases'])
    style_guide.personality_traits = json.dumps(analysis['personality_traits'])
    style_guide.message_patterns = json.dumps(analysis['message_patterns'])
    style_guide.special_elements = json.dumps(analysis['special_elements'])
    style_guide.style_notes = json.dumps(analysis['style_notes'])
    style_guide.last_analyzed = datetime.utcnow()
    
    db.commit()
    
    return analysis

def get_style_guide(business_id: int, db: Session) -> dict:
    """Retrieve the complete style guide for a business"""
    style_guide = db.query(BusinessOwnerStyle).filter(
        BusinessOwnerStyle.business_id == business_id
    ).first()
    
    if not style_guide:
        return {}
    
    return style_guide.style_guide

def learn_from_edit(original: str, edited: str, business_id: int, db: Session):
    """Learn from manual edits to improve style understanding"""
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    prompt = f"""
    Analyze how this message was edited to improve style matching:
    
    Original: {original}
    Edited: {edited}
    
    What specific changes were made to better match the owner's voice?
    Return as JSON with these keys:
    1. added_elements: What was added to improve authenticity
    2. removed_elements: What was removed that didn't match their voice
    3. structural_changes: How the message structure was modified
    4. tone_adjustments: How the tone was adjusted
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )
    
    changes = json.loads(response.choices[0].message.content)
    
    # Update style guide with new learnings
    style_guide = db.query(BusinessOwnerStyle).filter(
        BusinessOwnerStyle.business_id == business_id
    ).first()
    
    if style_guide:
        current_notes = json.loads(style_guide.style_notes) if style_guide.style_notes else {}
        current_notes['learned_from_edits'] = current_notes.get('learned_from_edits', [])
        current_notes['learned_from_edits'].append(changes)
        style_guide.style_notes = json.dumps(current_notes)
        db.commit()