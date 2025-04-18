import openai
import os
import json

def generate_onboarding_preview(business_name, business_goal, industry="", customer_name="there"):
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    goals = business_goal.split(", ")
    goal_phrase = ", ".join(goals[:-1]) + (" and " + goals[-1] if len(goals) > 1 else goals[0])

    prompt = f"""
You are the SMS writing expert for a business named {business_name}, which operates in the {industry or 'general'} industry.
Their goal is: {goal_phrase.lower()}.
You are helping them write a personalized SMS message to a customer named {customer_name}.

The SMS should:
- Reflect the business's voice and services (e.g. loans, therapy, listings)
- Be tailored to the industry
- Align with the goal of "{goal_phrase.lower()}"
- Be one sentence long
- Be warm, human, and friendly
- use emojis sparingly
- signature using {business_name} at the end

Example (for a loan company aiming to get referrals):
"Hi Jane, we hope you're loving your lower mortgage payment! If you know anyone looking to refinance, we'd love to help."

Now write the SMS:
"""

    print("📦 Onboarding Preview Prompt:")
    print(json.dumps({
        "business_name": business_name,
        "business_goal": business_goal,
        "industry": industry,
        "customer_name": customer_name
    }, indent=2))

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    print("🧠 LLM response for onboarding preview:")
    print(response.choices[0].message.content)

    return response.choices[0].message.content.strip()
