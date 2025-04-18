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
    Generates a response for the given SMS message using OpenAI's GPT model via chat completions.
    """
    if client is None:
        return "Error: OpenAI API key not configured."

    # Define the messages for the conversation
    business_name = business.business_name if business else "the business"
    business_tone = "friendly and professional"
    services = business.primary_services if business and business.primary_services else "our services"
    rep_name = business.representative_name if business else "someone from our team"

    customer_name = customer.customer_name if customer and hasattr(
        customer, "customer_name") else "the customer"
    lifecycle_stage = customer.lifecycle_stage if customer and customer.lifecycle_stage else "a potential customer"
    pain_points = customer.pain_points if customer and customer.pain_points else "no specific pain points mentioned"
    interaction_history = customer.interaction_history if customer and customer.interaction_history else "no prior interactions"

    system_content = f"You are a virtual assistant for a business called '{business_name}'. " \
        f"The business offers {services} and aims to be {business.business_goal or 'customer-focused'}. " \
        f"Respond with a {business_tone} tone and act as if you're representing {rep_name}. " \
        f"You are currently interacting with '{customer_name}', who is in the '{lifecycle_stage}' stage. " \
        f"Their known pain points are: '{pain_points}'. " \
        f"Here's a summary of their previous interactions: '{interaction_history}'. " \
        f"Use this context to provide the most helpful and relevant response. " \
        f"When starting your response, if you know the customer's name ('{customer_name}'), " \
        f"begin with a friendly greeting like 'Hello {customer_name}!' or 'Hi {customer_name},'. " \
        f"If the customer's name is 'the customer', then use a general greeting like 'Hello!' or 'Hi there,'. "

    messages = [
        {
            "role": "system",
            "content": system_content
        },
        {
            "role": "user",
            "content": f"The customer '{customer_name}' just sent this message: '{message}'. " \
            f"Write a reply that reflects the business tone, values, and helps the customer, considering their current stage, pain points, and past interactions."
        }
    ]

    # Make the API call using the pre-initialized client
    response = client.chat.completions.create(
        model="gpt-4o",  # Use the correct model (gpt-4o or gpt-4)
        messages=messages,  # Pass the conversation messages as an argument
        temperature=0.7,
        max_tokens=50,  # Increased max tokens to allow for more detailed responses
    )

    # Accessing the response object correctly
    ai_reply = response.choices[0].message.content.strip()

    return ai_reply