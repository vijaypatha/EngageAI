import openai
import os

def generate_sms(
    business_type,
    customer_name,
    event,
    sample_messages,
    lifecycle_stage,
    pain_points,
    interaction_history,
    representative_name="Your Name",
    business_goal="build strong customer relationships",
    preferred_tone="warm and helpful"
):
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = f"""
You're helping {representative_name}, a warm and sincere {business_type} business owner, text a customer named {customer_name}.

Context:
- Customer Stage: {lifecycle_stage}
- Pain Points: {pain_points}
- Interaction History: {interaction_history}
- Business Goal: {business_goal}
- Preferred Tone: {preferred_tone}

Here are a few of {representative_name}’s previous messages:
{sample_messages}

Write a short, warm, human SMS message that:
- Feels real, not robotic or overly polished
- Acknowledges the context or event (“{event}”)
- Builds trust or connection
- Can include a soft sign-off (“– {representative_name}”) or none
- Stays under 160 characters

Only return the raw message text.
"""


    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    return response.choices[0].message.content.strip()
