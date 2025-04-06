import openai
import os
import json  # needed for logging prompt input

def generate_sms_roadmap(
    business_type,
    customer_name,
    lifecycle_stage,
    pain_points,
    interaction_history,
    tone_examples,
    representative_name=None,
    business_name=None,
    business_goal="build strong customer relationships",
    primary_services="general services",
    preferred_tone="conversational and friendly"
):
    if representative_name is None:
        representative_name = "Your Name"
    if business_name is None:
      business_name = "Your Business"

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = f"""
You are an AI writing **4 short SMS messages** for a small business owner named {representative_name}, who runs a {business_type} business.

Each message is meant to:
- Reconnect with a customer named {customer_name}
- Sound natural, friendly, and personal
- Be grounded only in the facts provided — DO NOT assume any past events or conversations
- Bridge lightly between relationship and business, without being salesy

---

📇 Business Info:
- Services: {primary_services}
- Goal: {business_goal}
- Tone Style: {preferred_tone}

👤 Customer Info:
- Name: {customer_name}
- Lifecycle Stage: {lifecycle_stage}
- Pain Points: {pain_points}
- Interaction History: {interaction_history}

✍️ Style Guide:
- Use this tone style based on examples from {representative_name}:
{tone_examples}

- Vary your greetings across messages
- Keep messages under 160 characters
- Use contractions and natural phrasing
- Every SMS must end with a signature in this format: “– {representative_name}, {business_name}”
- Don’t hard-sell or push — be light, human, and sincere
- Messages should feel like a check-in or helpful nudge

⚠️ Do NOT invent any past events or conversations. Use only what’s given above. If unsure, keep it neutral and warm.

---

Return a JSON array of 4 objects. Each must include:
- "SMS Number"
- "smsContent"
- "smsTiming": e.g., "Day 3, 10:00 AM" — required and must match this format exactly
- "dayOffset": e.g., 3, 10, 17, 24
- "relevance": Why this message makes sense now
- "successIndicator": What would be a good result
- "whatif_customer_does_not_respond": Polite follow-up suggestion

Respond ONLY with a valid JSON array. Do not include commentary, markdown, or explanation.
"""


    # 🔍 Log the prompt inputs
    print("📦 Prompt data for LLM:")
    print(json.dumps({
        "customer_name": customer_name,
        "lifecycle_stage": lifecycle_stage,
        "pain_points": pain_points,
        "interaction_history": interaction_history,
        "tone_examples": tone_examples,
    }, indent=2))

    # 🔁 Call OpenAI
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    # 🧠 Log the raw LLM response
    print("🧠 LLM raw response:")
    print(response.choices[0].message.content)

    return response.choices[0].message.content.strip()
