# backend/app/services/ai_service.py
import re
import json
import logging
from datetime import datetime, timedelta, time, timezone # Added timezone
from typing import Dict, Any, Optional
import pytz

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import openai

from app.models import Customer, BusinessProfile, RoadmapMessage, MessageStatusEnum 
from app.schemas import RoadmapGenerate, RoadmapResponse, RoadmapMessageResponse
from app.config import settings
from app.services.style_service import StyleService 
from app.timezone_utils import get_business_timezone

logger = logging.getLogger(__name__)

# --- Helper Function: parse_customer_notes (V5 - Stricter Month Day, More Logging) ---
def parse_customer_notes(notes: str) -> dict:
    parsed_info: Dict[str, Any] = {}
    if not notes:
        logger.debug("AI_SERVICE_PN_V5: Notes string is empty.")
        return parsed_info
    
    notes_lower = notes.lower()
    logger.info(f"AI_SERVICE_PN_V5: Attempting to parse notes: '{notes_lower}'")
    
    found_birthday = False
    # Month name map for robust matching
    month_map = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
        'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'october': 10, 'oct': 10,
        'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }
    
    # Pattern 1: Explicit "Month Day" (e.g., "birthday on august 31", "bday is mar 1st")
    # Requires at least 3 letters for month name. \b for word boundaries.
    month_day_pattern = r'\b(?:birthday|bday)\s*(?:is|on)?\s*([a-zA-Z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\b'
    
    # Pattern 2: MM/DD or M/D (e.g., "birthday is 08/31", "bday: 3/5")
    mm_dd_pattern = r'\b(?:birthday|bday)\s*(?:is|on)?\s*(\d{1,2})\s*\/\s*(\d{1,2})\b'

    patterns_to_try = [
        ("Month-Day", month_day_pattern),
        ("MM/DD", mm_dd_pattern)
    ]

    for p_name, pattern in patterns_to_try:
        if found_birthday: break
        logger.debug(f"AI_SERVICE_PN_V5: Testing '{p_name}' pattern: {pattern}")

        for match in re.finditer(pattern, notes_lower):
            if found_birthday: break
            
            groups = match.groups()
            logger.debug(f"AI_SERVICE_PN_V5: '{p_name}' pattern matched. Groups: {groups}")
            
            month_input_str: Optional[str] = None
            day_input_str: Optional[str] = None

            if len(groups) == 2:
                month_input_str, day_input_str = groups[0], groups[1]
            else:
                logger.warning(f"AI_SERVICE_PN_V5: Pattern '{p_name}' expected 2 groups, got {len(groups)}. Skipping.")
                continue

            if not month_input_str or not day_input_str:
                logger.warning(f"AI_SERVICE_PN_V5: Empty month/day str from '{p_name}'. Month='{month_input_str}', Day='{day_input_str}'. Skipping.")
                continue
                
            logger.info(f"AI_SERVICE_PN_V5: Potential birthday elements (from '{p_name}'): Month='{month_input_str}', Day='{day_input_str}'")

            try:
                day = int(day_input_str)
                month_num = None
                
                if p_name == "MM/DD": # Month string is a number
                     if month_input_str.isdigit():
                        month_num = int(month_input_str)
                     else:
                        logger.warning(f"AI_SERVICE_PN_V5: MM/DD pattern got non-digit month '{month_input_str}'. Skipping.")
                        continue
                else: # Month string is a name (Month-Day pattern)
                    month_lookup_key = month_input_str.lower().strip()
                    month_num = month_map.get(month_lookup_key) # Try full name
                    if not month_num and len(month_lookup_key) >= 3:
                        month_num = month_map.get(month_lookup_key[:3]) # Try 3-letter abbreviation
                    
                    if not month_num:
                        logger.warning(f"AI_SERVICE_PN_V5: Could not map month name '{month_input_str}' to number.")
                        continue
                
                logger.debug(f"AI_SERVICE_PN_V5: Parsed day={day}, month_num={month_num}")

                if month_num and 1 <= month_num <= 12 and 1 <= day <= 31:
                    parsed_info['birthday_month'] = month_num
                    parsed_info['birthday_day'] = day
                    today = datetime.now(timezone.utc).date()
                    current_year = today.year
                    try:
                        bday_this_year = datetime(current_year, month_num, day).date()
                        bday_next = bday_this_year if bday_this_year >= today else datetime(current_year + 1, month_num, day).date()
                        parsed_info['days_until_birthday'] = (bday_next - today).days
                        found_birthday = True
                        logger.info(f"AI_SERVICE_PN_V5: Birthday SUCCESS. Month:{month_num}, Day:{day}, DaysUntil:{parsed_info['days_until_birthday']}")
                        break 
                    except ValueError as ve_date:
                        logger.warning(f"AI_SERVICE_PN_V5: Invalid date for {month_num}/{day} (Year {current_year}). Error: {ve_date}. Storing raw.")
                        parsed_info['birthday_details_raw'] = f"Month_str '{month_input_str.strip()}', Day_str '{day_input_str.strip()}'"
                        found_birthday = True; break
                else:
                    logger.warning(f"AI_SERVICE_PN_V5: Parsed month/day out of valid range. MonthNum='{month_num}', Day='{day}'")
            except (ValueError, IndexError) as e:
                 logger.warning(f"AI_SERVICE_PN_V5: Error converting day/month: Month='{month_input_str}', Day='{day_input_str}'. Error: {e}")
                 continue 
    
    if not found_birthday:
        logger.info("AI_SERVICE_PN_V5: NO BIRTHDAY FOUND after all patterns.")
    
    # Holiday/Event Mentions
    mentioned_holidays_or_events = []
    holiday_keywords = {
        "Christmas": ["christmas", "xmas"], "New Year": ["new year", "new year's"],
        "July 4th": ["july 4th", "independence day", "fourth of july"],
        "Thanksgiving": ["thanksgiving"], "Easter": ["easter"],
        "Valentine's Day": ["valentine", "valentine's day"]
    }
    for holiday_name, keywords in holiday_keywords.items():
        if any(keyword in notes_lower for keyword in keywords):
            mentioned_holidays_or_events.append(holiday_name)
    if mentioned_holidays_or_events:
        parsed_info["mentioned_holidays_or_events"] = mentioned_holidays_or_events
        logger.info(f"AI_SERVICE_PN_V5: Notes mentioned: {', '.join(mentioned_holidays_or_events)}")
    
    logger.info(f"AI_SERVICE_PN_V5: Final parsed_info from notes: {parsed_info}") # Changed to INFO for visibility
    return parsed_info

# ... (parse_business_profile_for_campaigns remains the same as V2/previous) ...
def parse_business_profile_for_campaigns(business_goal: str, primary_services: str) -> dict:
    campaign_details = {
        "detected_sales_phrases": [], "discounts_mentioned": [],
        "product_focus_for_sales": [], "general_strategy": business_goal
    }
    text_to_search = (business_goal.lower() if business_goal else "") + " " + (primary_services.lower() if primary_services else "")
    sales_keywords = ["sale", "sales", "discount", "offer", "promo", "special", "off"]
    for keyword in sales_keywords:
        if keyword in text_to_search: campaign_details["detected_sales_phrases"].append(keyword)
    percentage_matches = re.findall(r'(\d{1,2}(?:-\d{1,2})?%?\s*(?:off|discount))', text_to_search)
    if percentage_matches: campaign_details["discounts_mentioned"].extend(percentage_matches)
    product_focus_matches = re.findall(r'(?:sale|discount|offer)s?[\s\w%-]*on\s+([\w\s]+?)(?:\s+for|\s+during|\s+on|\.|$)', text_to_search)
    if product_focus_matches: campaign_details["product_focus_for_sales"].extend([p.strip() for p in product_focus_matches])
    campaign_details["has_sales_info"] = bool(campaign_details["detected_sales_phrases"] or campaign_details["discounts_mentioned"])
    logger.info(f"AI_SERVICE_BCP: Parsed Campaign Details: {campaign_details}")
    return campaign_details

class AIService:
    def __init__(self, db: Session):
        self.db = db
        if not settings.OPENAI_API_KEY:
            logger.error("AI_SERVICE: ❌ OPENAI_API_KEY not configured.")
            raise ValueError("OpenAI API Key is not configured.")
        self.client = openai.Client(api_key=settings.OPENAI_API_KEY)

    async def generate_roadmap(self, data: RoadmapGenerate) -> RoadmapResponse:
        logger.info(f"AI_SERVICE_GR_V6: Starting roadmap generation for Customer ID: {data.customer_id}, Business ID: {data.business_id}")
        
        try:
            customer = self.db.query(Customer).filter(Customer.id == data.customer_id).first()
            if not customer:
                 logger.error(f"AI_SERVICE_GR_V6: Customer {data.customer_id} not found.")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {data.customer_id} not found")
            
            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == data.business_id).first()
            if not business:
                 logger.error(f"AI_SERVICE_GR_V6: Business {data.business_id} not found.")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business {data.business_id} not found")

            style_service = StyleService()
            class StyleWrapper:
                 def __init__(self, style_dict: Optional[Dict[str, Any]]): self.style_analysis = style_dict or {}
            
            try:
                style_guide_raw = await style_service.get_style_guide(business.id, self.db)
                style = StyleWrapper(style_guide_raw)
            except Exception as sg_exc:
                logger.error(f"AI_SERVICE_GR_V6: Failed to fetch style guide for business {business.id}: {sg_exc}", exc_info=True)
                style = StyleWrapper(None) 
            style_guide = style.style_analysis
            logger.debug(f"AI_SERVICE_GR_V6: Style guide for biz {business.id}: {json.dumps(style_guide, indent=2) if style_guide else 'None'}")

            extracted_campaign_info = parse_business_profile_for_campaigns(business.business_goal, business.primary_services)
            business_context = {
                "name": business.business_name, "industry": business.industry,
                "goal_text": business.business_goal, "primary_services_text": business.primary_services,
                "representative_name": business.representative_name or business.business_name,
                "extracted_campaign_info": extracted_campaign_info,
                "business_timezone": business.timezone or "UTC" 
            }
            customer_notes_text = customer.interaction_history if customer.interaction_history else ""
            # Add specific customer pain points and lifecycle to the notes text for parsing, if not already there
            if customer.pain_points and customer.pain_points.lower() not in customer_notes_text.lower():
                customer_notes_text += f"\nPain points: {customer.pain_points}"
            if customer.lifecycle_stage and customer.lifecycle_stage.lower() not in customer_notes_text.lower():
                 customer_notes_text += f"\nLifecycle stage: {customer.lifecycle_stage}"

            customer_notes_info = parse_customer_notes(customer_notes_text) # Use augmented notes

            customer_context = {
                "name": customer.customer_name, "lifecycle_stage": customer.lifecycle_stage,
                "pain_points": customer.pain_points, 
                "relationship_notes_and_instructions": customer_notes_text, # Pass the full augmented notes
                "parsed_notes_for_events": customer_notes_info, # Parsed specific events like birthday
                "customer_timezone": customer.timezone 
            }
            current_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            logger.debug(f"AI_SERVICE_GR_V6: Business Context: {json.dumps(business_context, indent=2)}")
            logger.info(f"AI_SERVICE_GR_V6: Customer Context (with parsed_notes): {json.dumps(customer_context, indent=2)}") # Changed to INFO
            logger.info(f"AI_SERVICE_GR_V6: Current UTC Date for AI: {current_date_str}")

            # --- AI Prompt V6 ---
            system_prompt_template = (
                "You are an expert SMS engagement strategist. Your goal is to create personalized SMS roadmaps that are **temporally and contextually precise**.\n\n"
                "CORE MISSION: Each message's `sms_text` MUST be appropriate for its specific calculated send date (`Current Date` + `days_from_today`). Imagine it's that send date and compose accordingly.\n\n"
                "RULES & GUIDELINES:\n"
                "1.  **Personalization:** Use 'Customer Profile' details. Avoid disliked activities. For general check-ins, keep messages positive and related to business services.\n"
                "2.  **Language:** Default to English unless 'Customer Profile -> relationship_notes_and_instructions' clearly indicates another language preference.\n"
                "3.  **Business Alignment:** Align with 'Business Profile -> goal_text' and 'extracted_campaign_info'.\n"
                "4.  **EVENT & TEMPORAL CONTEXT (VERY CRITICAL!):\n"
                "    * **Current Date Anchor:** The 'Current Date' is {current_date_str} (YYYY-MM-DD, UTC). All themes are relative to this. A message for 'Day 60' from {current_date_str} (e.g., mid-July if Current Date is mid-May) MUST have a summer theme.\n"
                "    * **Birthday (from `customer_context['parsed_notes_for_events']['days_until_birthday']`):\n**"
                "        - **Primary:** If `days_until_birthday` is available and >= 0, schedule ONE message with `days_from_today = customer_context['parsed_notes_for_events']['days_until_birthday']`. `sms_text` MUST be a direct 'Happy Birthday, {{customer_name}}!' (e.g., 'Happy Birthday, {{customer_name}}! Hope you and Buster have a wonderful day!').\n"
                "        - **Belated:** If `days_until_birthday` is -1 or -2, set `days_from_today = 0` (or 1) and send a 'Happy Belated Birthday!'.\n"
                "        - **Early (Optional & Secondary):** If plan has space AND `days_until_birthday` > 5, an *additional* early wish can be sent 2-3 days prior: `days_from_today = days_until_birthday - 3`. Text: 'Thinking of you for your birthday coming up soon, {{customer_name}}!'.\n"
                "        - **Priority:** A message ON the birthday takes precedence over generic check-ins for that day.\n"
                "    * **Major US Holidays (New Year's, July 4th, Thanksgiving, Christmas):\n**"
                "        a. Only consider these if they fall within the 6-9 month planning window from `Current Date`.\n"
                "        b. For each relevant holiday, create ONE message. `days_from_today` MUST schedule it 1-2 days *before or exactly on* the holiday's actual calendar date.\n"
                "        c. `sms_text` MUST be appropriate for *that specific holiday and send date*. E.g., for July 4th, if sending July 3rd: 'Hope you have a great July 4th!'. If sending July 4th: 'Happy July 4th!'. **STRICTLY AVOID** pre-holiday language *after* the holiday (e.g., no 'Getting ready for July 4th' on July 5th. Instead, say 'Hope you had a great 4th!' or shift topic). Similarly, a 'New Year's' greeting is for late Dec/Jan 1, NOT early Dec.\n"
                "        d. Sales Info: Integrate if `Business Profile -> extracted_campaign_info -> has_sales_info` is true for that holiday period.\n"
                "5.  **Quarterly Check-ins (User Instruction: 'Send a nudge once every quarter'):** This is a KEY requirement. Schedule general check-ins approx. every 90 days from `Current Date` (e.g., 'Day 7-10' for first, then 'Day 90-95', 'Day 180-185'). `sms_text` MUST be seasonally appropriate for its send date. E.g., if `Current Date` is May and `days_from_today` results in December, theme for winter/holidays, NOT 'fall'.\n"
                "6.  **Style Adherence:** Perfectly match 'Business Owner Communication Style'.\n"
                "**MANDATORY TEMPORAL REASONING STEPS FOR EACH MESSAGE GENERATED:**\n"
                "    1. Calculate Send Date: `Current Date` ({current_date_str}) + AI's chosen `days_from_today`.\n"
                "    2. Identify Send Date's Calendar Context: What is the actual month, day, and season of this Send Date?\n"
                "    3. Check for Specific Events on Send Date: Is it a birthday (from `parsed_notes_for_events`)? A major US holiday?\n"
                "    4. Determine Message Theme: If specific event, theme for that event *as experienced on that Send Date*. If not, theme for the general season of the Send Date.\n"
                "    5. Verify Language: Ensure wording (e.g., 'Getting ready for...', 'Hope you had a great...') is appropriate for the Send Date relative to any event. NO PRE-EVENT LANGUAGE AFTER THE EVENT HAS PASSED.\n"
                "TECHNICAL REQUIREMENTS:\n"
                "1. Output ONLY a valid JSON object: `{{\"messages\": [{{...}}]}}`. No other text/markdown.\n"
                "2. 'messages' list: 3 to 5 message objects.\n"
                "3. Each message object: `days_from_today` (Integer >= 0), `sms_text` (String, theme MUST match send date context), `purpose` (String, e.g., 'Quarterly Check-in - Summer Update', 'Thanksgiving Greeting with Offer', 'Birthday Wish - On the Day').\n"
                "4. `sms_text` <160 chars, signature: '- {representative_name} from {business_name}'.\n"
            ).format(representative_name=business_context['representative_name'], business_name=business_context['name'], current_date_str=current_date_str)

            user_prompt_content = f"""
Current Date (UTC): {current_date_str}

Business Profile:
{json.dumps(business_context, indent=2)}

Customer Profile (includes `parsed_notes_for_events` like `days_until_birthday`. If `days_until_birthday` exists, prioritize a message ON that day):
{json.dumps(customer_context, indent=2)} 

Business Owner Communication Style:
{json.dumps(style_guide, indent=2)}
---
User Specific Instruction for Customer: "Send a nudge once every quarter and on big holidays. Jane is a school administrator seeking way to automate parent communication."

TASK:
Determine preferred language from 'Customer Profile -> relationship_notes_and_instructions'. Default to English.
Generate a 6-9 month SMS plan (3-5 messages).

Prioritize messages as per System Instructions (Birthday ON the day, then relevant Holidays, then Quarterly Check-ins).
ALL messages' `sms_text` MUST be thematically and seasonally **perfectly aligned** with their calculated send date.

**AVOID THESE EXAMPLES (Current Date is {current_date_str}):**
* If a message is for `days_from_today` resulting in Dec 2nd: DO NOT mention 'fall plans'. Theme for early winter.
* If a message is for `days_from_today` resulting in July 5th: DO NOT say 'Getting ready for July 4th'. Say 'Hope you had a great 4th!' or similar.
* If `parsed_notes_for_events.days_until_birthday` indicates Aug 31st is the birthday, the message for `days_from_today` that lands on Aug 31st MUST be 'Happy Birthday!', not a generic check-in.

Output ONLY the JSON object: {{"messages": [...]}}. Each object: {{"days_from_today": int, "sms_text": str, "purpose": str}}.
"""
            messages_for_openai = [
                {"role": "system", "content": system_prompt_template},
                {"role": "user", "content": user_prompt_content}
            ]
            
            logger.info(f"AI_SERVICE_GR_V6: Sending request to OpenAI for customer {data.customer_id} (biz: {data.business_id}) with V6 prompt.")
            # logger.debug(f"AI_SERVICE_GR_V6: Full V6 System Prompt: {formatted_system_prompt}")
            # logger.debug(f"AI_SERVICE_GR_V6: Full V6 User Prompt: {user_prompt_content}")

            response = self.client.chat.completions.create(
                model="gpt-4o", messages=messages_for_openai, response_format={"type": "json_object"} 
            )
            content = response.choices[0].message.content
            logger.info(f"AI_SERVICE_GR_V6: OpenAI raw V6 response snippet: {content[:500]}...")
            
            # ... (The rest of your JSON parsing, DB storage, date calculation, and error handling from V5 full code) ...
            # This part should remain the same, as the prompt is the primary change area.
            try:
                ai_response = json.loads(content)
                if not isinstance(ai_response, dict):
                    logger.error("AI_SERVICE_GR_V6: AI response not JSON object.")
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI response not JSON object.")
                ai_message_list = ai_response.get("messages")
                if not isinstance(ai_message_list, list):
                    logger.error("AI_SERVICE_GR_V6: 'messages' key not list or missing.")
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI response missing 'messages' list.")
            except json.JSONDecodeError as de:
                 logger.error(f"AI_SERVICE_GR_V6: Failed to parse OpenAI JSON: {de}. Content: {content[:500]}...")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI invalid JSON.")
            
            logger.info(f"AI_SERVICE_GR_V6: Parsed AI JSON. Processing {len(ai_message_list)} items.")
            roadmap_drafts_for_response = []
            business_tz_str = business.timezone or "UTC"
            business_tz = get_business_timezone(business_tz_str)
            successful_parses = 0

            for idx, msg_data in enumerate(ai_message_list):
                log_msg_prefix = f"AI_SERVICE_GR_V6: Draft Item {idx+1}/{len(ai_message_list)}"
                if not isinstance(msg_data, dict): 
                    logger.warning(f"{log_msg_prefix}: Skipping invalid item (not dict): {str(msg_data)[:100]}...")
                    continue
                sms_text = msg_data.get("sms_text")
                days_offset_str = msg_data.get("days_from_today")
                purpose = msg_data.get("purpose")
                if not isinstance(sms_text, str) or days_offset_str is None or purpose is None:
                    logger.warning(f"{log_msg_prefix}: Missing essential fields. Data: {str(msg_data)[:100]}...")
                    continue
                try:
                    days_offset = int(days_offset_str)
                    if days_offset < 0: days_offset = 0
                except ValueError:
                    logger.warning(f"{log_msg_prefix}: Invalid 'days_from_today' ({days_offset_str}). Skipping.")
                    continue
                try:
                    base_utc = datetime.strptime(current_date_str, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
                    target_utc_dt_exact = base_utc + timedelta(days=days_offset)
                    local_time_obj = time(10,0,0)
                    naive_local_dt = datetime.combine(target_utc_dt_exact.date(), local_time_obj)
                    localized_dt = business_tz.localize(naive_local_dt)
                    scheduled_utc = localized_dt.astimezone(pytz.UTC)
                    logger.debug(f"{log_msg_prefix}: SendUTC: {scheduled_utc.isoformat()} for: {purpose}")
                except Exception as e_date:
                    logger.error(f"{log_msg_prefix}: Date calc error: {e_date}", exc_info=True)
                    scheduled_utc = datetime.now(timezone.utc) + timedelta(days=idx+1, hours=1) # Changed here
                    logger.warning(f"{log_msg_prefix}: Fallback SendUTC: {scheduled_utc.isoformat()}")

                draft = RoadmapMessage(
                    customer_id=customer.id, business_id=business.id, smsContent=sms_text[:1600], 
                    smsTiming=f"{days_offset} days from today", send_datetime_utc=scheduled_utc,
                    status=MessageStatusEnum.DRAFT.value, relevance=str(purpose), message_id=None 
                )
                self.db.add(draft)
                try: self.db.flush(); self.db.refresh(draft) 
                except Exception as e_flush: self.db.rollback(); logger.error(f"{log_msg_prefix}: DB Error flushing: {e_flush}", exc_info=True); continue 
                try:
                    roadmap_drafts_for_response.append(RoadmapMessageResponse.model_validate(draft))
                    successful_parses += 1 
                except Exception as e_val: logger.error(f"{log_msg_prefix}: Pydantic validation draft ID {draft.id} failed: {e_val}", exc_info=True)
            
            if successful_parses > 0:
                try: self.db.commit(); logger.info(f"AI_SERVICE_GR_V6: Committed {successful_parses} drafts for cust {data.customer_id}.")
                except Exception as e_commit: self.db.rollback(); logger.error(f"AI_SERVICE_GR_V6: DB Commit Error: {e_commit}", exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save drafts.")
            
            final_msg = f"Roadmap processed. {successful_parses} drafts created."
            if successful_parses == 0 and len(ai_message_list) > 0: final_msg = "AI returned messages, but none were valid."
            elif len(ai_message_list) == 0: final_msg = "AI did not return any messages."

            return RoadmapResponse(
                status="success" if successful_parses > 0 or len(ai_message_list) == 0 else "error",
                message=final_msg, roadmap=roadmap_drafts_for_response,
                total_messages=successful_parses, customer_info=customer_context, business_info=business_context
            )
        
        except HTTPException as http_exc: 
            logger.error(f"AI_SERVICE_GR_V6: HTTPException: {http_exc.detail}", exc_info=True)
            if self.db.is_active: self.db.rollback() 
            raise http_exc
        except openai.OpenAIError as ai_error: 
             if self.db.is_active: self.db.rollback()
             logger.error(f"AI_SERVICE_GR_V6: OpenAI API Error: {ai_error}", exc_info=True)
             raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"AI service error: {str(ai_error)}")
        except Exception as e: 
            if self.db.is_active: self.db.rollback()
            logger.exception(f"AI_SERVICE_GR_V6: Unexpected Error for customer {data.customer_id}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal error: {str(e)}")

    async def generate_sms_response(self, message: str, customer_id: int, business_id: int) -> Dict[str, Any]:
        # ... (This method remains unchanged from your V5 version)
        logger.info(f"AI_SERVICE_GSR: Generating SMS response for incoming message. Customer ID: {customer_id}, Business ID: {business_id}")
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            logger.error(f"AI_SERVICE_GSR: Customer {customer_id} not found for SMS response generation.")
            raise HTTPException(status_code=404, detail="Customer not found")
        business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
        if not business:
            logger.error(f"AI_SERVICE_GSR: Business {business_id} not found for SMS response generation.")
            raise HTTPException(status_code=404, detail="Business not found")
        
        style_service = StyleService()
        class StyleWrapper: 
            def __init__(self, style_dict: Optional[Dict[str, Any]]): self.style_analysis = style_dict or {}
        
        try:
            style_guide_raw = await style_service.get_style_guide(business.id, self.db)
            style = StyleWrapper(style_guide_raw)
        except Exception as sg_exc:
            logger.error(f"AI_SERVICE_GSR: Failed to fetch style guide for business {business.id} during SMS response: {sg_exc}", exc_info=True)
            style = StyleWrapper(None) 
        
        style_guide = style.style_analysis
        logger.debug(f"AI_SERVICE_GSR: Style guide for SMS response: {json.dumps(style_guide, indent=2) if style_guide else 'No style guide.'}")

        rep_name = business.representative_name or business.business_name
        user_notes_for_reply = customer.interaction_history or ""
        reply_language_instruction = "Please reply in English." 
        if "spanish" in user_notes_for_reply.lower() or "español" in user_notes_for_reply.lower(): reply_language_instruction = "Please reply in Spanish."
        elif "chinese" in user_notes_for_reply.lower() or "mandarin" in user_notes_for_reply.lower(): reply_language_instruction = "Please reply in Chinese (Mandarin)."
        elif "portuguese" in user_notes_for_reply.lower() or "português" in user_notes_for_reply.lower(): reply_language_instruction = "Please reply in Portuguese."
        elif "telugu" in user_notes_for_reply.lower(): reply_language_instruction = "Please reply in Telugu."

        faq_context_str = ""
        is_faq_type_request = False 
        faq_data_dict: Dict[str, Any] = {} 

        if business.enable_ai_faq_auto_reply and business.structured_faq_data: 
            logger.info(f"AI_SERVICE_GSR: FAQ Auto-Reply active for Biz ID {business.id} during SMS response.") 
            faq_data_dict = business.structured_faq_data if isinstance(business.structured_faq_data, dict) else {}
            lower_message = message.lower()
            address_keywords = ["address", "location", "where are you", "where is your office", "directions"]
            hours_keywords = ["hours", "open", "close", "operating hours", "when are you open"]
            website_keywords = ["website", "site", "url", "web page"]

            if any(keyword in lower_message for keyword in address_keywords) and faq_data_dict.get('address'):
                is_faq_type_request = True; faq_context_str += f"\n- Address: {faq_data_dict.get('address')}"
            if any(keyword in lower_message for keyword in hours_keywords) and faq_data_dict.get('operating_hours'):
                is_faq_type_request = True; faq_context_str += f"\n- Hours: {faq_data_dict.get('operating_hours')}"
            if any(keyword in lower_message for keyword in website_keywords) and faq_data_dict.get('website'):
                is_faq_type_request = True; faq_context_str += f"\n- Website: {faq_data_dict.get('website')}"
            
            custom_faqs = faq_data_dict.get('custom_faqs', [])
            if custom_faqs and isinstance(custom_faqs, list): 
                custom_faq_match_found = False; temp_custom_faq_context = "\n\nCustom Q&As:"
                for item_any in custom_faqs: 
                    if isinstance(item_any, dict): 
                        q = item_any.get('question', '').lower()
                        if q and (q in lower_message or lower_message in q or any(kw in lower_message for kw in q.split() if len(kw)>3)): 
                            is_faq_type_request = True; custom_faq_match_found = True
                            temp_custom_faq_context += f"\n  - Q: {item_any.get('question')}\n    A: {item_any.get('answer')}"
                if custom_faq_match_found: faq_context_str += temp_custom_faq_context
            
            if is_faq_type_request: logger.info(f"AI_SERVICE_GSR: FAQ request detected. Context: {faq_context_str}")
            elif business.enable_ai_faq_auto_reply : 
                logger.info("AI_SERVICE_GSR: Autopilot ON, providing all FAQ data for general context.")
                if faq_data_dict.get('address'): faq_context_str += f"\n- Business address: {faq_data_dict.get('address')}"
                if faq_data_dict.get('operating_hours'): faq_context_str += f"\n- Operating hours: {faq_data_dict.get('operating_hours')}"
                if faq_data_dict.get('website'): faq_context_str += f"\n- Website: {faq_data_dict.get('website')}"
                if custom_faqs and isinstance(custom_faqs, list):
                    faq_context_str += "\n\nOther potentially relevant Q&As (general context):" 
                    for item_any_gen in custom_faqs: 
                        if isinstance(item_any_gen, dict):
                             faq_context_str += f"\n  - Q: {item_any_gen.get('question')} -> A: {item_any_gen.get('answer')}"

        prompt_parts = [
            f"You are a friendly assistant for {business.business_name}, a {business.industry} business.",
            f"The owner is {rep_name} and prefers this style: {json.dumps(style_guide, indent=2)}",
            f"Customer: {customer.customer_name}. Notes: '{user_notes_for_reply}'.",
            f"Customer's message: \"{message}\"",
            reply_language_instruction 
        ]
        faq_marker = "##FAQ_ANSWERED_FOR_DIRECT_REPLY##" 
        if business.enable_ai_faq_auto_reply and faq_context_str: 
            prompt_parts.extend([
                f"\n\nIMPORTANT CONTEXT (FAQs if applicable):{faq_context_str}",
                f"If you directly answer using the FAQ context, append '{faq_marker}' to your reply. Otherwise, do not append it.",
                "If FAQ context doesn't fully answer, have a natural conversation or say you'll get help. Don't invent non-FAQ info."
            ])
        prompt_parts.append(f"\n\nRESPONSE GUIDELINES: Draft a friendly, natural SMS reply (<160 chars). Adhere to owner's style. Sign off as \"- {rep_name}\".")
        if not (business.enable_ai_faq_auto_reply and is_faq_type_request): 
             prompt_parts.append("Avoid promotions unless directly asked or highly relevant.")

        prompt = "\n".join(prompt_parts)
        logger.debug(f"AI_SERVICE_GSR: Prompt for Biz {business.id}:\n{prompt[:1000]}...") 
        
        response = self.client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "system", "content": "Craft helpful SMS replies."}, {"role": "user", "content": prompt}],
            max_tokens=100 
        )
        raw_content = response.choices[0].message.content.strip()
        answered_as_faq = bool(business.enable_ai_faq_auto_reply and raw_content.endswith(faq_marker))
        final_content = raw_content[:-len(faq_marker)].strip() if answered_as_faq else raw_content
        
        logger.info(f"AI_SERVICE_GSR: AI reply for Biz {business.id}: '{final_content}'. FAQ Autopilot: {answered_as_faq}")
        return {"text": final_content, "is_faq_answer": answered_as_faq, "ai_should_reply_directly_as_faq": answered_as_faq}

    async def analyze_customer_response(self, customer_id: int, message: str) -> dict:
        logger.warning("AI_SERVICE_ACR: analyze_customer_response not fully implemented yet.")
        return {"sentiment": "unknown", "next_step": "review_manually"}