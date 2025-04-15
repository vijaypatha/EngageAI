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
IMPORTANT: Your reply must be under 80 characters. No long texts.

Write a short, warm, human SMS message that:
- Feels real, not robotic or overly polished
- Acknowledges the context or event (“{event}”)
- Builds trust or connection
- Can include a soft sign-off (“– {representative_name}”) or none

Context:
- Customer Stage: {lifecycle_stage}
- Pain Points: {pain_points}
- Interaction History: {interaction_history}
- Business Goal: {business_goal}
- Preferred Tone: {preferred_tone}

Here are a few of {representative_name}’s previous messages:
{sample_messages}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=60,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant that writes short, real SMS messages."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    final = response.choices[0].message.content.strip()
    return final if len(final) <= 80 else final[:77] + "..."
