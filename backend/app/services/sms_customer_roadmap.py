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

The timing of these messages should be determined by any specific scheduling instructions found in the `interaction_history` or other customer information. For example: 
- "Birthday is April 25. Send 1 message per month"
- "Follow up weekly"
- "Send something encouraging around Thanksgiving"

If no specific timing is found, default to a reasonable weekly cadence: (dayOffsets: 0, 7, 14, 21).

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
- Messages should feel like a check-in or helpful nudge — never robotic
- Avoid generic content — make each message feel relevant to the timing or context

🧠 Voice Matching:
The business owner wants these messages to sound like *they* wrote them personally.

- Match their voice, vocabulary, and phrasing.
- Review the tone examples provided above and write in that style.
- Avoid robotic, overly formal, or generic phrasing.
- SMS should feel like it's coming straight from the business owner’s phone — natural, personal, and human.

💌 Personal Touch:
Many business owners want their customers to feel remembered, especially during meaningful or joyful life moments — such as birthdays, holidays, or anniversaries. If events like these are mentioned in the customer info, you should:
- Center one or more messages around those moments
- Adjust your spacing/frequency as needed to make the timing feel intentional and caring

⚠️ Timing Logic:
- Inspect all customer info (especially interaction history) for cues like: "monthly check-in", "birthday April 25", "follow up after onboarding"
- Use those cues to decide each message’s `smsTiming` and `dayOffset`
- You may vary spacing (e.g., weekly, monthly) based on what's appropriate for that customer
- If no timing logic is found, use default dayOffsets: 0, 7, 14, 21
- Always set dayOffset=0 for the first message in the sequence

---

Return a JSON array of 4 objects. Each must include:
- "SMS Number"
- "smsContent"
- "smsTiming": A friendly description of when to send it (e.g., "On Birthday (April 25), 10:00 AM" or "30 days after message 1, 10:00 AM")
- "dayOffset": Integer days from the first message
- "relevance": Why this message fits that timing
- "successIndicator": What would be a good result
- "whatif_customer_does_not_respond": Polite next step suggestion

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
