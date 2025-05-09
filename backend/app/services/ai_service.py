# backend/app/services/ai_service.py
import re
import json
import logging
from datetime import datetime, timedelta, time
import pytz

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import openai

from app.models import Customer, BusinessProfile, RoadmapMessage
from app.schemas import RoadmapGenerate, RoadmapResponse, RoadmapMessageResponse
from app.config import settings
from app.services.style_service import StyleService
from app.timezone_utils import get_business_timezone

logger = logging.getLogger(__name__)

def parse_customer_notes(notes: str) -> dict:
    """
    Parses customer interaction history notes for key information like birthday.
    """
    parsed_info = {}
    if not notes:
        return parsed_info

    notes_lower = notes.lower()
    birthday_patterns = [
        r'(?:birthday|bday)\s*(?:is|on)?\s+([a-zA-Z]+)\s+(\d{1,2})(?:st|nd|rd|th)?', 
        r'(\d{1,2})/(\d{1,2})\s+birthday'
    ]
    found_birthday = False
    for pattern in birthday_patterns:
        birthday_match = re.search(pattern, notes_lower)
        if birthday_match:
            groups = birthday_match.groups()
            month_str, day_str = groups[0], groups[1]
            try:
                day = int(day_str)
                month_num = None
                if month_str.isdigit():
                    month_num = int(month_str)
                else:
                    month_map = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                                 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
                    month_num = month_map.get(month_str[:3])
                if month_num and 1 <= month_num <= 12 and 1 <= day <= 31:
                    parsed_info['birthday_month'] = month_num
                    parsed_info['birthday_day'] = day
                    today = datetime.utcnow().date()
                    current_year = today.year
                    try:
                        next_birthday_dt = datetime(current_year, month_num, day)
                        next_birthday = next_birthday_dt.date()
                        if next_birthday < today:
                            next_birthday = datetime(current_year + 1, month_num, day).date()
                        parsed_info['days_until_birthday'] = (next_birthday - today).days
                        found_birthday = True
                        break
                    except ValueError:
                        logger.warning(f"Could not calculate days for birthday {month_num}/{day}. Date might be invalid.")
                        parsed_info['birthday_details'] = f"Month {month_num}, Day {day} (could not validate precisely)"
                        found_birthday = True
                        break
            except (ValueError, IndexError):
                 logger.warning(f"Could not parse birthday fragment: Month='{month_str}', Day='{day_str}'")
                 continue
    return parsed_info


class AIService:
    def __init__(self, db: Session):
        self.db = db
        if not settings.OPENAI_API_KEY:
            logger.error("❌ OPENAI_API_KEY not configured in settings.")
            raise ValueError("OpenAI API Key is not configured.")
        self.client = openai.Client(api_key=settings.OPENAI_API_KEY)

    async def generate_roadmap(self, data: RoadmapGenerate) -> RoadmapResponse:
        try:
            customer = self.db.query(Customer).filter(Customer.id == data.customer_id).first()
            if not customer:
                 logger.warning(f"Customer not found for ID: {data.customer_id}")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer with ID {data.customer_id} not found")
            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == data.business_id).first()
            if not business:
                 logger.warning(f"Business not found for ID: {data.business_id}")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with ID {data.business_id} not found")

            style_service = StyleService()
            class StyleWrapper:
                 def __init__(self, style_dict):
                    self.style_analysis = style_dict or {}
            style = StyleWrapper(await style_service.get_style_guide(business.id, self.db))
            style_guide = style.style_analysis if style and style.style_analysis else {}

            business_context = {
                "name": business.business_name,
                "industry": business.industry,
                "goal": business.business_goal,
                "services": business.primary_services,
                "representative_name": business.representative_name or business.business_name
            }
            customer_notes_info = parse_customer_notes(customer.interaction_history)
            customer_context = {
                "name": customer.customer_name,
                "lifecycle_stage": customer.lifecycle_stage,
                "pain_points": customer.pain_points,
                "relationship_notes": customer.interaction_history,
                "parsed_notes": customer_notes_info
            }
            preferred_language = "Spanish" if "spanish" in (customer.interaction_history or "").lower() else "English"
            current_date_str = datetime.utcnow().strftime("%Y-%m-%d")

            # --- Generalized and Refined OpenAI Prompt ---
            messages_for_openai = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert SMS engagement strategist for small businesses. Your goal is to create thoughtful, personalized SMS roadmaps that genuinely connect with customers and align with the business's objectives. You must strictly follow all instructions and use the provided data accurately.\n\n"
                        "GENERAL PRINCIPLES:\n"
                        "1.  **Data-Driven Personalization:** The 'Customer Profile' (especially 'relationship_notes', 'pain_points', and 'parsed_notes') is paramount. Your messages MUST reflect this data. If 'relationship_notes' indicate a dislike (e.g., 'Doesn't Bike'), NEVER suggest that activity. If no specific interests are noted for general check-ins, keep messages broadly positive and supportive, related to the business's services without making assumptions.\n"
                        "2.  **Business Goal Alignment:** The 'Business Profile -> goal' dictates the strategy. This includes message frequency (e.g., 'monthly', 'quarterly'), holiday messaging strategy (e.g., 'sales on holidays'), and the overall purpose of the engagement (e.g., 'growth', 'retention').\n"
                        "3.  **Event-Specific Messaging Rules:**\n"
                        "    * **Birthdays:** Purely warm wishes, 3-5 days prior, using 'parsed_notes' for dates.\n"
                        "    * **Holidays:** Warm greetings, 1-3 days prior. CRITICALLY: If 'Business Profile -> goal' mentions 'sales', 'promotions', or 'offers' for holidays, you MUST incorporate a brief, natural mention of relevant holiday offers. Otherwise, holiday messages are for greetings ONLY.\n"
                        "4.  **Style Adherence:** Perfectly match the 'Business Owner Communication Style'.\n"
                        "5.  **Technical Requirements:** End with signature ('- {representative_name} from {business_name}'), keep SMS under 160 chars, calculate 'days_from_today' from 'Current Date' ({current_date_str}), and output ONLY the specified JSON.\n\n"
                        "INTERPRETING 'Business Profile -> goal':\n"
                        "- If goal mentions a specific check-in frequency (e.g., 'Send messages Once a month'), prioritize this for general check-ins (approx. 30 days for monthly, 90 for quarterly).\n"
                        "- If goal mentions 'sales during big holidays', apply this to holiday message content as per rule #3.\n"
                        "- If goal mentions 'growth', non-event messages can gently remind about services. For 'retention', focus on relationship building.\n"
                    ).format(representative_name=business_context['representative_name'], business_name=business_context['name'], current_date_str=current_date_str)
                },
                {
                    "role": "user",
                    "content": f"""
Current Date: {current_date_str}

Business Profile:
{json.dumps(business_context, indent=2)}

Customer Profile:
{json.dumps(customer_context, indent=2)} 

Business Owner Communication Style:
{json.dumps(style_guide, indent=2)}

Language Preference:
{preferred_language}

---

TASK:

Generate a comprehensive and personalized SMS engagement plan for the customer for the next 6-9 months. This plan must strictly follow the strategy outlined in 'Business Profile -> goal' and all system instructions.

The plan should thoughtfully integrate:
A.  **Regular Check-ins:** At the frequency specified in 'Business Profile -> goal'. If no frequency is given, default to quarterly (approx. every 90 days).
B.  **Birthday Message:** If birthday information is available in 'Customer Profile -> parsed_notes', schedule one 3-5 days prior.
C.  **Holiday Messages:** For relevant major US holidays (e.g., Memorial Day, July 4th, Labor Day, Thanksgiving, Christmas, New Year's Day) that fall within the plan's timeframe. Schedule these 1-3 days before the holiday. The content must reflect the holiday sales strategy from 'Business Profile -> goal' (see system instruction #3).
D.  **Content Sensitivity:** Ensure all messages are sensitive to 'Customer Profile -> relationship_notes' and 'pain_points'. Do NOT suggest activities the customer dislikes or is not noted to be interested in.

For each message, calculate 'days_from_today' accurately based on the '{current_date_str}' and the event date.
Ensure distinct holidays (e.g., Christmas and New Year's) have separate, appropriately timed messages. Avoid redundancy.
The "purpose" field should clearly state the reason for the message (e.g., "Monthly Check-in based on Business Goal", "Thanksgiving Greetings with Holiday Offer", "Birthday Well-wishes").

Output ONLY the JSON object with the 'messages' array.
"""
                }
            ]
            
            logger.info(f"ℹ️ Sending request to OpenAI for customer {data.customer_id}, business {data.business_id}")
            # logger.debug(f"🧠 OpenAI Prompt: {json.dumps(messages_for_openai, indent=2)}")
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages_for_openai,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            logger.info("🧠 OpenAI raw response: %s", content)
            try:
                ai_response = json.loads(content)
                if not isinstance(ai_response, dict):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON format (not an object)")
                ai_message_list = ai_response.get("messages")
                if not isinstance(ai_message_list, list):
                     if ai_message_list is None and isinstance(ai_response.get("message"), str):
                         logger.warning("AI returned a single message object instead of a list. Wrapping it.")
                         ai_message_list = [ai_response]
                     else:
                         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON format ('messages' key not a list or missing)")
            except json.JSONDecodeError as decode_error:
                 logger.error(f"❌ Failed to parse OpenAI response JSON: {decode_error} - Content: {content}")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON content")
            except Exception as parse_exc:
                 logger.error(f"❌ Error processing AI response structure: {parse_exc}")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error processing AI response: {parse_exc}")

            logger.info(f"✅ Successfully parsed {len(ai_message_list)} messages from AI.")

            roadmap_drafts_for_response = []
            business_tz_str = business.timezone or "UTC"
            business_tz = get_business_timezone(business_tz_str)
            logger.info(f"ℹ️ Processing {len(ai_message_list)} DRAFT messages using Business Timezone: {business_tz_str}")

            for idx, msg_data in enumerate(ai_message_list):
                if not isinstance(msg_data, dict) or not all(k in msg_data for k in ["message", "days_from_today", "purpose"]):
                    logger.warning(f"⚠️ Skipping invalid draft message item at index {idx}: {msg_data}")
                    continue
                try:
                    days_from_today = int(msg_data.get("days_from_today"))
                    if days_from_today < 0:
                         logger.warning(f"⚠️ AI returned negative days_from_today ({days_from_today}), using 0 instead.")
                         days_from_today = 0
                    target_date_utc = (datetime.utcnow() + timedelta(days=days_from_today)).date()
                    target_local_time = time(10, 0, 0) # Default to 10:00 AM
                    naive_local_dt = datetime.combine(target_date_utc, target_local_time)
                    localized_dt = business_tz.localize(naive_local_dt)
                    scheduled_time_utc = localized_dt.astimezone(pytz.UTC)
                    logger.debug(f"  Draft {idx+1}: days={days_from_today} -> ScheduledUTC={scheduled_time_utc}")
                except (ValueError, TypeError, KeyError) as e:
                    logger.error(f"❌ Error calculating scheduled time for draft (days_from_today='{msg_data.get('days_from_today')}', index={idx}): {e}. Falling back.")
                    base_time = datetime.utcnow()
                    scheduled_time_utc = base_time + timedelta(days=int(msg_data.get("days_from_today", idx + 1)))
                message_content = str(msg_data.get("message", ""))[:160]
                roadmap_draft = RoadmapMessage(
                    customer_id=customer.id,
                    business_id=business.id,
                    smsContent=message_content,
                    smsTiming=f"{days_from_today} days from today",
                    send_datetime_utc=scheduled_time_utc,
                    status="draft",
                    relevance=str(msg_data.get("purpose", "Customer engagement")),
                    message_id=None
                )
                self.db.add(roadmap_draft)
                try:
                    self.db.flush()
                    self.db.refresh(roadmap_draft)
                except Exception as rm_flush_exc:
                     self.db.rollback()
                     logger.exception(f"❌ DB Error flushing roadmap draft: {rm_flush_exc}")
                     logger.error(f"Failing draft data: {msg_data}")
                     raise
                try:
                    response_draft_model = RoadmapMessageResponse.model_validate(roadmap_draft)
                    roadmap_drafts_for_response.append(response_draft_model)
                except Exception as validation_error:
                     logger.error(f"❌ Failed to validate RoadmapMessageResponse Pydantic model for draft ID {roadmap_draft.id}: {validation_error}")
            self.db.commit()
            logger.info(f"✅ Successfully created {len(roadmap_drafts_for_response)} roadmap DRAFTS in DB for customer {data.customer_id}.")
            return RoadmapResponse(
                status="success",
                message="Roadmap drafts generated successfully",
                roadmap=roadmap_drafts_for_response,
                total_messages=len(roadmap_drafts_for_response),
                customer_info=customer_context,
                business_info=business_context
            )
        except HTTPException as http_exc:
            logger.error(f"HTTP Error generating roadmap for customer {data.customer_id}: {http_exc.status_code} - {http_exc.detail}")
            self.db.rollback()
            raise http_exc
        except openai.OpenAIError as ai_error:
             self.db.rollback()
             logger.error(f"❌ OpenAI API Error generating roadmap for customer {data.customer_id}: {ai_error}")
             raise HTTPException(
                 status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                 detail=f"AI service error: {str(ai_error)}"
             )
        except Exception as e:
            self.db.rollback()
            logger.exception(f"❌ Unexpected Error generating roadmap for customer {data.customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An internal server error occurred while generating the roadmap drafts."
            )

    async def generate_sms_response(self, message: str, customer_id: int, business_id: int) -> str:
        # ... (generate_sms_response method remains the same as you provided) ...
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        style_service = StyleService()
        class StyleWrapper:
            def __init__(self, style_dict): self.style_analysis = style_dict or {}
        style = StyleWrapper(await style_service.get_style_guide(business.id, self.db))
        style_guide = style.style_analysis if style and style.style_analysis else {}
        rep_name = business.representative_name or business.business_name
        prompt = f"""
You are a friendly assistant for {business.business_name}, a {business.industry} business.

The business owner is {rep_name} and prefers this tone and style:
{json.dumps(style_guide, indent=2)}

The customer is {customer.customer_name}, who previously shared:
{customer.interaction_history or "No interaction history."}

They just sent this message:
"{message}"

Please draft a friendly, natural-sounding SMS reply that fits the business tone and maintains the relationship. Keep it under 160 characters. Do not include promotions unless relevant.
Always sign off with the business owner's name like: "- {rep_name}".
"""
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You craft helpful and friendly SMS replies."},
                      {"role": "user", "content": prompt}],
            max_tokens=100
        )
        content = response.choices[0].message.content.strip()
        logger.info(f"🧠 One-off AI reply generated for customer {customer_id}: {content}")
        return content

    async def analyze_customer_response(self, customer_id: int, message: str) -> dict:
        # ... (analyze_customer_response method remains the same as you provided) ...
        logger.warning("analyze_customer_response not fully implemented yet.")
        pass
        return {"sentiment": "unknown", "next_step": "review_manually"}