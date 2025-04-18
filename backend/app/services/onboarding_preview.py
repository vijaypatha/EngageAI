import openai
import os
import json

def generate_onboarding_preview(business_name, business_goal, industry="", customer_name="there"):
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    goals = business_goal.split(", ")
    goal_phrase = ", ".join(goals[:-1]) + (" and " + goals[-1] if len(goals) > 1 else goals[0])

    prompt = f"""
You are helping a business named {business_name} in the {industry or 'general'} industry.
Their goal is to {goal_phrase.lower()}.
Generate a short, friendly SMS they might send to a customer named {customer_name}.

Make it warm and human. No emojis. No signatures. One sentence only.
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
