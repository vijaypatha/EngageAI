import openai
import os
from sqlalchemy.orm import Session
from app.models import BusinessProfile
from app.models import BusinessOwnerStyle


def generate_scenarios(business_id: int, db: Session):
    # Retrieve business profile
    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        return []

    industry = business.industry
    services = business.primary_services

    # Optimized AI prompt
    prompt = f"""
    You are a customer interested in a {industry} business that offers {services}. 
    Based on common customer behavior, generate 3 realistic SMS messages that a customer 
    might send to this business. Ensure the questions:
    - Are natural and conversational
    - Reflect common concerns in this industry
    - Cover different interaction stages (first-time inquiry, follow-up, complaint, etc.)

    Format:
    1. [Customer question]
    2. [Customer question]
    3. [Customer question]
    """

    # Use OpenAI client correctly
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    # Extract scenarios from response
    raw_output = response.choices[0].message.content.strip()
    scenarios = [s.strip() for s in raw_output.split("\n") if s.strip()]

    return scenarios


def get_owner_style_samples(business_id: int, db: Session) -> str:
    responses = db.query(BusinessOwnerStyle).filter(BusinessOwnerStyle.business_id == business_id).all()
    if not responses:
        return "No sample messages available."
    return "\n".join([f"Customer: {r.scenario}\nOwner: {r.response}" for r in responses])

