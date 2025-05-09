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
    # ... (parse_customer_notes function for birthday, etc., remains the same)
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
                        logger.warning(f"Could not calculate days for birthday {month_num}/{day}.")
                        parsed_info['birthday_details'] = f"Month {month_num}, Day {day} (invalid date)"
                        found_birthday = True
                        break
            except (ValueError, IndexError):
                 logger.warning(f"Could not parse birthday fragment: Month='{month_str}', Day='{day_str}'")
                 continue
    return parsed_info

def parse_business_profile_for_campaigns(business_goal: str, primary_services: str) -> dict:
    # ... (parse_business_profile_for_campaigns function remains the same)
    campaign_details = {
        "detected_sales_phrases": [],
        "discounts_mentioned": [],
        "product_focus_for_sales": [],
        "general_strategy": business_goal
    }
    text_to_search = (business_goal.lower() if business_goal else "") + " " + (primary_services.lower() if primary_services else "")
    sales_keywords = ["sale", "sales", "discount", "offer", "promo", "special", "off"]
    for keyword in sales_keywords:
        if keyword in text_to_search:
            campaign_details["detected_sales_phrases"].append(keyword)
    percentage_matches = re.findall(r'(\d{1,2}(?:-\d{1,2})?%?\s*(?:off|discount))', text_to_search)
    if percentage_matches:
        campaign_details["discounts_mentioned"].extend(percentage_matches)
    product_focus_matches = re.findall(r'(?:sale|discount|offer)s?[\s\w%-]*on\s+([\w\s]+?)(?:\s+for|\s+during|\s+on|\.|$)', text_to_search)
    if product_focus_matches:
        campaign_details["product_focus_for_sales"].extend([p.strip() for p in product_focus_matches])
    if campaign_details["detected_sales_phrases"] or campaign_details["discounts_mentioned"]:
        campaign_details["has_sales_info"] = True
    else:
        campaign_details["has_sales_info"] = False
    logger.info(f"Parsed Campaign Details from Business Profile: {campaign_details}")
    return campaign_details


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
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer with ID {data.customer_id} not found")
            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == data.business_id).first()
            if not business:
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with ID {data.business_id} not found")

            style_service = StyleService()
            class StyleWrapper:
                 def __init__(self, style_dict): self.style_analysis = style_dict or {}
            style = StyleWrapper(await style_service.get_style_guide(business.id, self.db))
            style_guide = style.style_analysis if style and style.style_analysis else {}

            extracted_campaign_info = parse_business_profile_for_campaigns(
                business.business_goal,
                business.primary_services
            )
            business_context = {
                "name": business.business_name,
                "industry": business.industry,
                "goal_text": business.business_goal,
                "primary_services_text": business.primary_services,
                "representative_name": business.representative_name or business.business_name,
                "extracted_campaign_info": extracted_campaign_info
            }
            customer_notes_info = parse_customer_notes(customer.interaction_history)
            customer_context = {
                "name": customer.customer_name,
                "lifecycle_stage": customer.lifecycle_stage,
                "pain_points": customer.pain_points,
                "relationship_notes": customer.interaction_history, # This is where language notes would be
                "parsed_notes": customer_notes_info
            }
            # REMOVED: Python-based preferred_language detection
            # preferred_language = "Spanish" if "spanish" in (customer.interaction_history or "").lower() else "English"
            current_date_str = datetime.utcnow().strftime("%Y-%m-%d")

            # --- MODIFIED: AI Prompt for AI-driven language detection ---
            messages_for_openai = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert SMS engagement strategist for small businesses. Your goal is to create thoughtful, personalized SMS roadmaps that genuinely connect with customers and align with the business's objectives. You must strictly follow all instructions and use the provided data accurately.\n\n"
                        "GENERAL PRINCIPLES:\n"
                        "1.  **Data-Driven Personalization:** The 'Customer Profile' (especially 'relationship_notes', 'pain_points', and 'parsed_notes') is paramount. Your messages MUST reflect this data. If 'relationship_notes' indicate a dislike (e.g., 'Doesn't Bike'), NEVER suggest that activity. If no specific interests are noted for general check-ins, keep messages broadly positive and supportive, related to the business's services without making assumptions.\n"
                        "2.  **Language Determination:** Carefully analyze 'Customer Profile -> relationship_notes' to determine if a preferred communication language other than English is explicitly stated or strongly implied (e.g., 'prefers Spanish', 'communicates in Mandarin', 'customer is from Brazil'). If a clear preference for a specific language is found, ALL generated SMS messages for this customer MUST be in that language. If no such preference is clear, default to English.\n"
                        "3.  **Business Goal & Campaign Alignment:** The 'Business Profile -> goal_text' and 'extracted_campaign_info' dictate the strategy. This includes message frequency, holiday messaging strategy (including any sales details from 'extracted_campaign_info'), and the overall purpose.\n"
                        "4.  **Event-Specific Messaging Rules:**\n"
                        "    * **Birthdays:** Purely warm wishes, 3-5 days prior, using 'parsed_notes' for dates.\n"
                        "    * **Holidays:** Warm greetings, 1-3 days prior. CRITICALLY: If 'Business Profile -> extracted_campaign_info -> has_sales_info' is true, you MUST try to incorporate sales details mentioned in 'discounts_mentioned' or 'product_focus_for_sales' into the holiday messages naturally. If specific details are missing from extraction but 'has_sales_info' is true, use a placeholder like `[Check out our current holiday offers!]`. If 'has_sales_info' is false, holiday messages are for greetings ONLY.\n"
                        "5.  **Style Adherence:** Perfectly match the 'Business Owner Communication Style'.\n"
                        "6.  **Technical Requirements:** End with signature ('- {representative_name} from {business_name}'), keep SMS under 160 chars, calculate 'days_from_today' from 'Current Date' ({current_date_str}), and output ONLY the specified JSON.\n\n"
                        "INTERPRETING 'Business Profile -> extracted_campaign_info':\n"
                        "- Use 'general_strategy' (the original business_goal text) for overall direction.\n"
                        "- If 'has_sales_info' is true, use 'discounts_mentioned' and 'product_focus_for_sales' to make holiday and promotional messages specific. If these details are vague in the extraction, create a compelling general sales message or use a placeholder for the owner to refine.\n"
                        "- Determine check-in frequency based on keywords like 'monthly' or 'quarterly' found in 'general_strategy'. Default to quarterly if unspecified.\n"
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

---

TASK:

First, determine the customer's preferred communication language by carefully analyzing the 'Customer Profile -> relationship_notes'. If a specific language (e.g., Spanish, Chinese, Portuguese, French) is mentioned or strongly implied as their preference, use that language for all SMS messages you generate. If no preference is found, default to English.

Then, generate a comprehensive and personalized SMS engagement plan for the customer in the determined language for the next 6-9 months. This plan must strictly follow the strategy outlined in 'Business Profile -> goal_text' and 'Business Profile -> extracted_campaign_info', and all system instructions.

The plan should thoughtfully integrate:
A.  **Regular Check-ins:** At the frequency indicated by 'Business Profile -> extracted_campaign_info -> general_strategy' or default to quarterly.
B.  **Birthday Message:** If birthday information is available in 'Customer Profile -> parsed_notes', schedule one 3-5 days prior.
C.  **Holiday Messages:** For relevant major US holidays. The content MUST reflect any sales strategy indicated in 'Business Profile -> extracted_campaign_info' (see system instruction #4 and the 'INTERPRETING' section). If specific extracted discounts are present, use them. If sales are generally indicated but specifics are not clear from extraction, craft a compelling generic sales message or use a placeholder like `[View our special holiday deals!]`.
D.  **Content Sensitivity:** Ensure all messages are sensitive to 'Customer Profile'. Do NOT suggest activities the customer dislikes or is not noted to be interested in.

For each message, calculate 'days_from_today' accurately. Ensure distinct holidays have separate, appropriately timed messages.
The "purpose" field should be descriptive (e.g., "Monthly Check-in", "Thanksgiving Greetings with Extracted Offer Details", "Birthday Well-wishes").

Output ONLY the JSON object with the 'messages' array.
"""
                }
            ]
            
            logger.info(f"ℹ️ Sending request to OpenAI for customer {data.customer_id}, business {data.business_id}")
            # logger.debug(f"🧠 OpenAI Prompt: {json.dumps(messages_for_openai, indent=2)}")
            response = self.client.chat.completions.create(
                model="gpt-4o", # Or your preferred model that's good with multilingual and instruction following
                messages=messages_for_openai,
                response_format={"type": "json_object"}
            )

            # ... (Rest of the parsing, draft creation, and error handling remains the same) ...
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
        # ... (generate_sms_response method remains the same) ...
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
        
        # AI-driven language detection for one-off replies too
        # This is a simplified version. For a full system, you might want to make this a helper.
        user_notes_for_reply = customer.interaction_history or ""
        reply_language_instruction = ""
        # Basic check for language keywords in notes for one-off replies
        if "spanish" in user_notes_for_reply.lower() or "español" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Spanish."
        elif "chinese" in user_notes_for_reply.lower() or "mandarin" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Chinese (Mandarin)."
        elif "portuguese" in user_notes_for_reply.lower() or "português" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Portuguese."
        elif "telugu" in user_notes_for_reply.lower() or "telugu" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Telugu."
        # Add more language detections if needed
        else:
            reply_language_instruction = "Please reply in English."


        prompt = f"""
You are a friendly assistant for {business.business_name}, a {business.industry} business.

The business owner is {rep_name} and prefers this tone and style:
{json.dumps(style_guide, indent=2)}

The customer is {customer.customer_name}, who previously shared:
{user_notes_for_reply}

They just sent this message:
"{message}"

{reply_language_instruction}
Draft a friendly, natural-sounding SMS reply that fits the business tone and maintains the relationship. Keep it under 160 characters. Do not include promotions unless relevant.
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
        logger.warning("analyze_customer_response not fully implemented yet.")
        return {"sentiment": "unknown", "next_step": "review_manually"}