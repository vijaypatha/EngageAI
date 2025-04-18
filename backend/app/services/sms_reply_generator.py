import openai
import os

# Initialize the OpenAI client at the module level
openai_api_key = os.getenv("OPENAI_API_KEY")
if openai_api_key:
    client = openai.OpenAI(api_key=openai_api_key)
else:
    client = None
    print("Warning: OPENAI_API_KEY environment variable not set. AI responses will not be generated.")

# Define and initialize twilio_phone_number
twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER")
if not twilio_phone_number:
    print("Warning: TWILIO_PHONE_NUMBER environment variable not set. Sending SMS will likely fail.")


def generate_ai_response(message: str, business=None, customer=None) -> str:
    """
    Generates a short SMS reply using OpenAI's GPT model with tone and structure constraints.
    """
    if client is None:
        return "Error: OpenAI API key not configured."

    business_name = business.business_name if business else "Your Business"
    rep_name = business.representative_name if business else "Someone from our team"
    services = business.primary_services if business and business.primary_services else "general services"
    business_goal = business.business_goal if business and business.business_goal else "build strong customer relationships"
    preferred_tone = "conversational and friendly"

    customer_name = customer.customer_name if customer and hasattr(customer, "customer_name") else "the customer"
    lifecycle_stage = customer.lifecycle_stage if customer and customer.lifecycle_stage else "a potential customer"
    pain_points = customer.pain_points if customer and customer.pain_points else "no known pain points"
    interaction_history = customer.interaction_history if customer and customer.interaction_history else "no prior interaction"

    prompt = f"""
You are an AI assistant helping {rep_name} from {business_name}, a business that provides {services} and aims to {business_goal}.

The customer you're replying to is named {customer_name}. They are currently in the "{lifecycle_stage}" stage. Known pain points: "{pain_points}". Interaction history: "{interaction_history}".

Your job is to write a friendly, short SMS in response to the customer's latest message:
"{message}"

✍️ Style Guide:
- Length: under 160 characters
- Tone: {preferred_tone}
- Be helpful but not salesy
- Start with a warm greeting using the customer name if available
- End with a signature like this: “– {rep_name}, {business_name}”
- Use contractions and natural phrasing
- Do NOT invent details or make assumptions

Respond with ONLY the SMS text. No JSON, no extra formatting.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.7,
        max_tokens=60
    )

    return response.choices[0].message.content.strip()