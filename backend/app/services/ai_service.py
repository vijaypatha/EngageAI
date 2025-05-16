# backend/app/services/ai_service.py
import re
import json
import logging
from datetime import datetime, timedelta, time # Ensure time is imported
from typing import Dict, Any, Optional # Ensure Optional is imported
import pytz # For timezone handling

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import openai

# Assuming Customer, BusinessProfile, RoadmapMessage are correctly imported from app.models
from app.models import Customer, BusinessProfile, RoadmapMessage, MessageStatusEnum 
from app.schemas import RoadmapGenerate, RoadmapResponse, RoadmapMessageResponse
from app.config import settings
# Assuming StyleService is correctly imported and get_style_guide is an async method
from app.services.style_service import StyleService 
# Import timezone utility
from app.timezone_utils import get_business_timezone

logger = logging.getLogger(__name__)

# Helper function to parse notes for special dates
def parse_customer_notes(notes: str) -> dict:
    parsed_info: Dict[str, Any] = {} # Added type hint
    if not notes:
        return parsed_info
    
    notes_lower = notes.lower()
    
    # Birthday parsing logic
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
                    month_num = month_map.get(month_str[:3].lower())

                if month_num and 1 <= month_num <= 12 and 1 <= day <= 31:
                    parsed_info['birthday_month'] = month_num
                    parsed_info['birthday_day'] = day
                    
                    today = datetime.utcnow().date() 
                    current_year = today.year
                    try:
                        next_birthday_dt = datetime(current_year, month_num, day)
                        next_birthday_date_obj = next_birthday_dt.date() # Use date object for comparison

                        if next_birthday_date_obj < today: 
                            next_birthday_date_obj = datetime(current_year + 1, month_num, day).date()
                        
                        parsed_info['days_until_birthday'] = (next_birthday_date_obj - today).days
                        found_birthday = True
                        logger.info(f"AI_SERVICE: Birthday parsed for customer. Month: {month_num}, Day: {day}. Days until: {parsed_info['days_until_birthday']}")
                        break 
                    except ValueError:
                        logger.warning(f"AI_SERVICE: Could not form a valid date for birthday {month_num}/{day} in year {current_year}. Storing raw parts.")
                        parsed_info['birthday_details_raw'] = f"Month {month_num}, Day {day}"
                        found_birthday = True 
                        break
            except (ValueError, IndexError):
                 logger.warning(f"AI_SERVICE: Could not parse birthday fragment: Month='{month_str}', Day='{day_str}'")
                 continue 
    
    if not found_birthday:
        logger.info("AI_SERVICE: No explicit birthday found in customer notes.")

    # General holiday/event mentions (simplified for this example)
    # Consider a more sophisticated way to pass event data if needed.
    # For now, just checking for keywords.
    # This information can help the AI decide if a generic holiday message is appropriate
    # if a specific holiday's date aligns with a scheduled message.
    mentioned_holidays = []
    if "christmas" in notes_lower: mentioned_holidays.append("Christmas")
    if "new year" in notes_lower: mentioned_holidays.append("New Year")
    if "july 4th" in notes_lower or "independence day" in notes_lower: mentioned_holidays.append("July 4th")
    if "thanksgiving" in notes_lower: mentioned_holidays.append("Thanksgiving")
    if "easter" in notes_lower: mentioned_holidays.append("Easter")
    if "valentine" in notes_lower: mentioned_holidays.append("Valentine's Day")

    if mentioned_holidays:
        parsed_info["mentioned_holidays_or_events"] = mentioned_holidays
        logger.info(f"AI_SERVICE: Customer notes mentioned holidays/events: {mentioned_holidays}")
    
    logger.debug(f"AI_SERVICE: Final parsed customer notes for AI prompt: {parsed_info}")
    return parsed_info

# Helper function to parse business profile (remains the same)
def parse_business_profile_for_campaigns(business_goal: str, primary_services: str) -> dict:
    # ... (exact same implementation as your provided code for this function) ...
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
    logger.info(f"AI_SERVICE: Parsed Campaign Details from Business Profile: {campaign_details}")
    return campaign_details

class AIService:
    def __init__(self, db: Session):
        self.db = db
        if not settings.OPENAI_API_KEY:
            logger.error("AI_SERVICE: ❌ OPENAI_API_KEY not configured in settings.")
            raise ValueError("OpenAI API Key is not configured.")
        self.client = openai.Client(api_key=settings.OPENAI_API_KEY)

    async def generate_roadmap(self, data: RoadmapGenerate) -> RoadmapResponse:
        logger.info(f"AI_SERVICE: Starting roadmap generation for Customer ID: {data.customer_id}, Business ID: {data.business_id}")
        
        try:
            customer = self.db.query(Customer).filter(Customer.id == data.customer_id).first()
            if not customer:
                 logger.error(f"AI_SERVICE: Customer with ID {data.customer_id} not found.")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer with ID {data.customer_id} not found")
            
            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == data.business_id).first()
            if not business:
                 logger.error(f"AI_SERVICE: Business with ID {data.business_id} not found.")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with ID {data.business_id} not found")

            style_service = StyleService()
            class StyleWrapper:
                 def __init__(self, style_dict: Optional[Dict[str, Any]]): self.style_analysis = style_dict or {}
            
            try:
                style_guide_raw = await style_service.get_style_guide(business.id, self.db)
                style = StyleWrapper(style_guide_raw)
            except Exception as sg_exc:
                logger.error(f"AI_SERVICE: Failed to fetch style guide for business {business.id}: {sg_exc}", exc_info=True)
                style = StyleWrapper(None)
            
            style_guide = style.style_analysis
            logger.debug(f"AI_SERVICE: Style guide loaded for business {business.id}: {json.dumps(style_guide, indent=2) if style_guide else 'No style guide found/used.'}")

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
                "extracted_campaign_info": extracted_campaign_info,
                "business_timezone": business.timezone or "UTC" 
            }
            customer_notes_info = parse_customer_notes(customer.interaction_history or "") # Ensure notes is not None
            customer_context = {
                "name": customer.customer_name,
                "lifecycle_stage": customer.lifecycle_stage,
                "pain_points": customer.pain_points,
                "relationship_notes": customer.interaction_history or "", # Ensure notes is not None
                "parsed_notes": customer_notes_info, # This will contain 'days_until_birthday' if found
                "customer_timezone": customer.timezone 
            }
            current_date_str = datetime.utcnow().strftime("%Y-%m-%d") 
            logger.debug(f"AI_SERVICE: Business Context for Prompt: {json.dumps(business_context, indent=2)}")
            logger.debug(f"AI_SERVICE: Customer Context for Prompt: {json.dumps(customer_context, indent=2)}")
            logger.info(f"AI_SERVICE: Current UTC Date for AI Context: {current_date_str}")

            # --- Enhanced AI Prompt V2 ---
            messages_for_openai = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert SMS engagement strategist for small businesses. Your goal is to create thoughtful, personalized SMS roadmaps that genuinely connect with customers and align with the business's objectives. You must strictly follow all instructions and use the provided data accurately.\n\n"
                        "CORE MISSION: Ensure every message is **temporally relevant** to its calculated send date (based on 'Current Date' + 'days_from_today') and contextually appropriate for the customer and business.\n\n"
                        "GENERAL PRINCIPLES:\n"
                        "1.  **Data-Driven Personalization:** Use 'Customer Profile' details. Avoid suggesting disliked activities. For general check-ins without specific customer interests, keep messages broadly positive and related to business services.\n"
                        "2.  **Language:** If 'Customer Profile -> relationship_notes' clearly indicates a language preference (e.g., Spanish), use that language for ALL messages. Otherwise, use English.\n"
                        "3.  **Business Goal Alignment:** Strategy is dictated by 'Business Profile -> goal_text' and 'extracted_campaign_info'.\n"
                        "4.  **EVENT-SPECIFIC MESSAGING & TEMPORAL CONTEXT (CRITICAL!):\n"
                        "    * **Current Date Anchor:** The 'Current Date' is {current_date_str} (YYYY-MM-DD, UTC). All message themes and content MUST be relevant to their future send date, calculated as `Current Date + 'days_from_today'`. A message for 'Day 60' from {current_date_str} should be themed for the season and context approximately 60 days from {current_date_str}. For example, if Current Date is May 15th, a message for 'Day 60' is around mid-July; its theme must reflect summer.\n"
                        "    * **Birthday (from `customer_context['parsed_notes']`):** If 'days_until_birthday' is available, schedule ONE birthday greeting. Calculate `days_from_today` to send this message exactly ON the birthday (i.e., `days_from_today = customer_context['parsed_notes']['days_until_birthday']`). The `sms_text` should be a direct 'Happy Birthday!' message. If 'days_until_birthday' suggests the birthday is today or has just passed by 1-2 days, still send a belated birthday wish for 'Day 0' or 'Day 1'. If 'days_until_birthday' means the birthday is 3-5 days away, you can send an 'early birthday' wish for `days_from_today = customer_context['parsed_notes']['days_until_birthday'] - X` (where X is 3, 4, or 5) with wording like 'Hope you have a great birthday coming up!'. If no birthday info, do not invent one.\n"
                        "    * **Major US Holidays (New Year's Day, July 4th, Thanksgiving, Christmas):**\n"
                        "        a. Identify if any of these holidays fall within the 6-9 month planning window from the `Current Date`.\n"
                        "        b. For each relevant upcoming holiday, create ONE message. The `days_from_today` for this message MUST position it to be sent 1-3 days *before or on* the actual holiday date.\n"
                        "        c. The `sms_text` theme MUST match the specific holiday and its proximity. Example: A 'Happy New Year!' message is for late Dec/Jan 1st. A 'Happy July 4th!' message for early July. DO NOT generate holiday messages for the wrong season/month (e.g., no July 4th messages in September if Current Date is May).\n"
                        "        d. If `Business Profile -> extracted_campaign_info -> has_sales_info` is true for that holiday period, integrate sales details from `discounts_mentioned` or `product_focus_for_sales`. If sales are generally indicated but specifics are missing, use a placeholder like `[Check out our special holiday deals!]`. If `has_sales_info` is false, holiday messages are for greetings ONLY.\n"
                        "5.  **Quarterly Check-ins:** The user note 'Send a nudge once every quarter' is a primary requirement. Schedule general check-in messages roughly every 90 days (e.g., 'Day 0', 'Day 90', 'Day 180'). The content of these check-ins MUST be seasonally appropriate for their calculated send date relative to the 'Current Date'.\n"
                        "6.  **Style Adherence:** Perfectly match the 'Business Owner Communication Style'.\n"
                        "TECHNICAL REQUIREMENTS:\n"
                        "1. Output ONLY a valid JSON object with a top-level key 'messages'. No other text.\n"
                        "2. 'messages' key must contain a list of 3 to 5 message objects.\n"
                        "3. Each message object MUST contain: 'days_from_today' (Integer >= 0), 'sms_text' (String, theme must match send date context), 'purpose' (String, descriptive).\n"
                        "4. 'sms_text' under 160 characters, ending with signature: '- {representative_name} from {business_name}'.\n"
                    ).format(representative_name=business_context['representative_name'], business_name=business_context['name'], current_date_str=current_date_str)
                },
                {
                    "role": "user",
                    "content": f"""
Current Date (UTC): {current_date_str}

Business Profile:
{json.dumps(business_context, indent=2)}

Customer Profile (includes 'parsed_notes' with potential 'days_until_birthday'):
{json.dumps(customer_context, indent=2)} 

Business Owner Communication Style:
{json.dumps(style_guide, indent=2)}
---
User Specific Instruction: "Send a nudge once every quarter and on big holidays."

TASK:
Determine preferred language from 'Customer Profile -> relationship_notes'. Default to English if none.
Generate a 6-9 month SMS plan (3-5 messages) in the determined language.
Prioritize:
1.  A birthday message if `parsed_notes.days_until_birthday` is available (sent ON the birthday or 3-5 days prior if `days_until_birthday` allows for an early greeting).
2.  Messages for major US holidays (New Year's, July 4th, Thanksgiving, Christmas) if they fall within the planning window, sent 1-3 days before/on the holiday.
3.  Quarterly check-in messages (approx. every 90 days from `Current Date`).
Ensure ALL messages ('sms_text') are thematically and seasonally appropriate for their calculated send date (`Current Date` + `days_from_today`).
The 'purpose' field should reflect the message's theme and timing.

Output ONLY the JSON object with 'messages' list.
"""
                }
            ]
            # --- End of Enhanced AI Prompt V2 ---
            
            logger.info(f"AI_SERVICE: Sending request to OpenAI for customer {data.customer_id} (biz: {data.business_id}) with V2 prompt.")
            # logger.debug(f"AI_SERVICE: Full prompt to OpenAI: {json.dumps(messages_for_openai, indent=2)}")

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages_for_openai,
                response_format={"type": "json_object"} 
            )

            content = response.choices[0].message.content
            logger.info(f"AI_SERVICE: OpenAI raw response content snippet: {content[:500]}...")

            try:
                ai_response = json.loads(content)
                if not isinstance(ai_response, dict):
                    logger.error("AI_SERVICE: AI response is not a JSON object.")
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI response was not a JSON object.")
                
                ai_message_list = ai_response.get("messages")
                if not isinstance(ai_message_list, list):
                    logger.error("AI_SERVICE: 'messages' key in AI response is not a list or is missing.")
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI response missing 'messages' list.")
            except json.JSONDecodeError as decode_error:
                 logger.error(f"AI_SERVICE: Failed to parse OpenAI JSON: {decode_error}. Content: {content[:500]}...")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON content.")
            
            logger.info(f"AI_SERVICE: Parsed AI JSON. Processing {len(ai_message_list)} message items.")

            roadmap_drafts_for_response = []
            business_tz_str = business.timezone or "UTC"
            business_tz = get_business_timezone(business_tz_str)
            successful_parses = 0

            for idx, msg_data in enumerate(ai_message_list):
                log_msg_prefix = f"AI_SERVICE: Processing Draft Item {idx+1}/{len(ai_message_list)}"
                if not isinstance(msg_data, dict): 
                    logger.warning(f"{log_msg_prefix}: Skipping invalid item (not a dict): {str(msg_data)[:100]}...")
                    continue

                message_text_from_ai = msg_data.get("sms_text") # Prioritize 'sms_text' as per prompt
                if not isinstance(message_text_from_ai, str):
                    logger.warning(f"{log_msg_prefix}: 'sms_text' key missing or not a string. Data: {str(msg_data)[:100]}...")
                    continue
                
                days_offset_str = msg_data.get("days_from_today")
                purpose = msg_data.get("purpose")

                if days_offset_str is None or purpose is None:
                    logger.warning(f"{log_msg_prefix}: Missing 'days_from_today' or 'purpose'. Data: {str(msg_data)[:100]}...")
                    continue
                
                try:
                    days_offset = int(days_offset_str)
                    if days_offset < 0:
                         logger.warning(f"{log_msg_prefix}: Negative days_offset ({days_offset}), using 0.")
                         days_offset = 0
                except ValueError:
                    logger.warning(f"{log_msg_prefix}: Invalid 'days_from_today' value ({days_offset_str}). Skipping.")
                    continue
                
                try:
                    base_utc_date_for_calc = datetime.strptime(current_date_str, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
                    target_utc_date_exact = base_utc_date_for_calc + timedelta(days=days_offset)
                    target_local_time_obj = time(10, 0, 0) 
                    naive_target_dt_in_business_tz = datetime.combine(target_utc_date_exact.date(), target_local_time_obj)
                    localized_target_dt_in_business_tz = business_tz.localize(naive_target_dt_in_business_tz)
                    scheduled_time_utc_final = localized_target_dt_in_business_tz.astimezone(pytz.UTC)
                    logger.debug(f"{log_msg_prefix}: Calculated send_datetime_utc: {scheduled_time_utc_final.isoformat()} for purpose: {purpose}")
                except Exception as date_calc_err:
                    logger.error(f"{log_msg_prefix}: Error in date calculation: {date_calc_err}", exc_info=True)
                    # Fallback to a noticeable future date to flag an issue, or skip
                    scheduled_time_utc_final = datetime.utcnow().replace(tzinfo=pytz.UTC) + timedelta(days=idx + 1, hours=1) # Fallback
                    logger.warning(f"{log_msg_prefix}: Using fallback scheduled_time_utc: {scheduled_time_utc_final.isoformat()}")


                roadmap_draft = RoadmapMessage(
                    customer_id=customer.id, business_id=business.id,
                    smsContent=message_text_from_ai[:1600], 
                    smsTiming=f"{days_offset} days from today",
                    send_datetime_utc=scheduled_time_utc_final,
                    status=MessageStatusEnum.DRAFT.value, 
                    relevance=str(purpose), message_id=None 
                )
                self.db.add(roadmap_draft)
                try:
                    self.db.flush() 
                    self.db.refresh(roadmap_draft) 
                except Exception as rm_flush_exc:
                     self.db.rollback()
                     logger.error(f"{log_msg_prefix}: DB Error flushing roadmap draft: {rm_flush_exc}", exc_info=True)
                     continue 
                
                try:
                    response_draft_model = RoadmapMessageResponse.from_orm(roadmap_draft) # Use from_orm
                    roadmap_drafts_for_response.append(response_draft_model)
                    successful_parses += 1 
                except Exception as validation_error: 
                     logger.error(f"{log_msg_prefix}: Pydantic validation failed for draft ID {roadmap_draft.id}: {validation_error}", exc_info=True)
            
            if successful_parses > 0:
                try:
                    self.db.commit()
                    logger.info(f"AI_SERVICE: Committed {successful_parses} drafts for customer {data.customer_id}.")
                except Exception as commit_exc:
                    self.db.rollback()
                    logger.error(f"AI_SERVICE: DB Error committing drafts: {commit_exc}", exc_info=True)
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save roadmap drafts.")
            
            final_status_message = f"Roadmap generation processed. {successful_parses} drafts created."
            if successful_parses == 0 and len(ai_message_list) > 0:
                final_status_message = "AI returned messages, but none could be processed into valid drafts. Please review AI output or prompt."
            elif len(ai_message_list) == 0:
                final_status_message = "AI did not return any messages to process for the roadmap."


            return RoadmapResponse(
                status="success" if successful_parses > 0 or len(ai_message_list) == 0 else "error",
                message=final_status_message,
                roadmap=roadmap_drafts_for_response,
                total_messages=successful_parses, 
                customer_info=customer_context,
                business_info=business_context
            )
        
        except HTTPException as http_exc: 
            logger.error(f"AI_SERVICE: HTTPException: {http_exc.detail}", exc_info=True)
            if self.db.is_active: self.db.rollback() 
            raise http_exc
        except openai.OpenAIError as ai_error: 
             if self.db.is_active: self.db.rollback()
             logger.error(f"AI_SERVICE: OpenAI API Error: {ai_error}", exc_info=True)
             raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"AI service error: {str(ai_error)}")
        except Exception as e: 
            if self.db.is_active: self.db.rollback()
            logger.exception(f"AI_SERVICE: Unexpected Error in generate_roadmap for customer {data.customer_id}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal error generating roadmap: {str(e)}")

    async def generate_sms_response(self, message: str, customer_id: int, business_id: int) -> Dict[str, Any]:
        # ... (This method remains unchanged from your previous version, as the primary issue was roadmap generation)
        logger.info(f"AI_SERVICE: Generating SMS response for incoming message. Customer ID: {customer_id}, Business ID: {business_id}")
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            logger.error(f"AI_SERVICE: Customer {customer_id} not found for SMS response generation.")
            raise HTTPException(status_code=404, detail="Customer not found")
        business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
        if not business:
            logger.error(f"AI_SERVICE: Business {business_id} not found for SMS response generation.")
            raise HTTPException(status_code=404, detail="Business not found")
        
        style_service = StyleService()
        class StyleWrapper: # Simplified wrapper
            def __init__(self, style_dict: Optional[Dict[str, Any]]): self.style_analysis = style_dict or {}
        
        try:
            style_guide_raw = await style_service.get_style_guide(business.id, self.db)
            style = StyleWrapper(style_guide_raw)
        except Exception as sg_exc:
            logger.error(f"AI_SERVICE: Failed to fetch style guide for business {business.id} during SMS response: {sg_exc}", exc_info=True)
            style = StyleWrapper(None) # Default to empty style guide on error
        
        style_guide = style.style_analysis
        logger.debug(f"AI_SERVICE: Style guide for SMS response: {json.dumps(style_guide, indent=2) if style_guide else 'No style guide.'}")

        rep_name = business.representative_name or business.business_name
        
        user_notes_for_reply = customer.interaction_history or ""
        reply_language_instruction = "" # Default to English
        # Simple language detection from notes
        if "spanish" in user_notes_for_reply.lower() or "español" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Spanish."
        elif "chinese" in user_notes_for_reply.lower() or "mandarin" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Chinese (Mandarin)."
        elif "portuguese" in user_notes_for_reply.lower() or "português" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Portuguese."
        elif "telugu" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Telugu."
        else:
            reply_language_instruction = "Please reply in English."

        faq_context_str = ""
        is_faq_type_request = False 
        faq_data_dict: Dict[str, Any] = {} # Ensure faq_data_dict is always a dict

        if business.enable_ai_faq_auto_reply and business.structured_faq_data: 
            logger.info(f"AI_SERVICE: FAQ Auto-Reply logic active for Business ID {business.id} during SMS response.") 
            # Ensure structured_faq_data is treated as a dict
            faq_data_dict = business.structured_faq_data if isinstance(business.structured_faq_data, dict) else {}
            
            lower_message = message.lower()
            address_keywords = ["address", "location", "where are you", "where is your office", "directions"]
            hours_keywords = ["hours", "open", "close", "operating hours", "when are you open"]
            website_keywords = ["website", "site", "url", "web page"]

            if any(keyword in lower_message for keyword in address_keywords) and faq_data_dict.get('address'):
                is_faq_type_request = True
                faq_context_str += f"\n- The business address is: {faq_data_dict.get('address')}"
            if any(keyword in lower_message for keyword in hours_keywords) and faq_data_dict.get('operating_hours'):
                is_faq_type_request = True
                faq_context_str += f"\n- Operating hours: {faq_data_dict.get('operating_hours')}"
            if any(keyword in lower_message for keyword in website_keywords) and faq_data_dict.get('website'):
                is_faq_type_request = True
                faq_context_str += f"\n- Website: {faq_data_dict.get('website')}"
            
            custom_faqs = faq_data_dict.get('custom_faqs', [])
            if custom_faqs and isinstance(custom_faqs, list): 
                custom_faq_match_found = False
                temp_custom_faq_context = "\n\nCustom Q&As available:"
                for faq_item_any in custom_faqs: 
                    if isinstance(faq_item_any, dict): 
                        faq_item = faq_item_any 
                        question_text = faq_item.get('question', '').lower()
                        if question_text and (question_text in lower_message or lower_message in question_text or any(keyword in lower_message for keyword in question_text.split() if len(keyword)>3)): 
                            is_faq_type_request = True 
                            custom_faq_match_found = True
                            temp_custom_faq_context += f"\n  - Q: {faq_item.get('question')}\n    A: {faq_item.get('answer')}"
                    else:
                        logger.warning(f"AI_SERVICE: Encountered non-dictionary item in custom_faqs: {faq_item_any}")

                if custom_faq_match_found:
                    faq_context_str += temp_custom_faq_context
            
            if is_faq_type_request: 
                logger.info(f"AI_SERVICE: Potential FAQ request detected for SMS response. Context: {faq_context_str}")
            elif business.enable_ai_faq_auto_reply : 
                logger.info("AI_SERVICE: Message not a direct FAQ type, but AI Autopilot ON. Providing all FAQ data for SMS response context.")
                if faq_data_dict.get('address'): faq_context_str += f"\n- Business address: {faq_data_dict.get('address')}"
                if faq_data_dict.get('operating_hours'): faq_context_str += f"\n- Operating hours: {faq_data_dict.get('operating_hours')}"
                if faq_data_dict.get('website'): faq_context_str += f"\n- Website: {faq_data_dict.get('website')}"
                if custom_faqs and isinstance(custom_faqs, list):
                    faq_context_str += "\n\nOther potentially relevant Q&As (general context):" 
                    for faq_item_any in custom_faqs: 
                        if isinstance(faq_item_any, dict):
                             faq_context_str += f"\n  - Q: {faq_item_any.get('question')} -> A: {faq_item_any.get('answer')}"


        prompt_parts = [
            f"You are a friendly assistant for {business.business_name}, a {business.industry} business.",
            f"The business owner is {rep_name} and prefers this tone and style (follow it closely):",
            json.dumps(style_guide, indent=2),
            f"\nThe customer is {customer.customer_name}. Previous interactions/notes: '{user_notes_for_reply}'.",
            f"\nThe customer just sent this message: \"{message}\"",
            reply_language_instruction 
        ]

        faq_marker = "##FAQ_ANSWERED_FOR_DIRECT_REPLY##" 

        if business.enable_ai_faq_auto_reply and faq_context_str: 
            prompt_parts.append(f"\n\nIMPORTANT CONTEXTUAL BUSINESS INFORMATION (for FAQs if applicable):")
            prompt_parts.append(faq_context_str)
            prompt_parts.append(f"\nIf you use any of the above contextual business information to directly and completely answer the customer's question, append the exact marker '{faq_marker}' to the VERY END of your reply. Otherwise, do NOT append the marker.")
            prompt_parts.append("If you cannot directly answer with the provided FAQ information, have a natural, helpful conversation or indicate you will get assistance for their specific query. Do not makeup information not in the FAQ context.")
        
        prompt_parts.append(f"\n\nRESPONSE GUIDELINES: Draft a friendly, natural-sounding SMS reply. Keep it under 160 characters. Adhere to the owner's style. Sign off as \"- {rep_name}\".")
        if not (business.enable_ai_faq_auto_reply and is_faq_type_request): 
             prompt_parts.append("Avoid promotions unless directly asked or highly relevant to their query.")

        prompt = "\n".join(prompt_parts)
        logger.debug(f"AI_SERVICE: generate_sms_response PROMPT for Business ID {business.id}:\n{prompt[:1000]}...") 
        
        response = self.client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "system", "content": "You craft helpful and friendly SMS replies based on provided context and instructions."},
                      {"role": "user", "content": prompt}],
            max_tokens=100 
        )
        
        raw_generated_content = response.choices[0].message.content.strip()
        
        answered_as_faq_by_ai = False 
        final_content_for_sms = raw_generated_content

        if business.enable_ai_faq_auto_reply and raw_generated_content.endswith(faq_marker): 
            answered_as_faq_by_ai = True
            final_content_for_sms = raw_generated_content[:-len(faq_marker)].strip() 
            logger.info(f"AI_SERVICE: AI indicated FAQ was answered for direct reply (marker found). Business ID: {business.id}. Cleaned SMS: '{final_content_for_sms}'")
        else:
            logger.info(f"AI_SERVICE: AI direct reply processed. Business ID: {business.id}. SMS: '{final_content_for_sms}'. FAQ Autopilot Engaged for Direct Reply: {answered_as_faq_by_ai}")

        return {
            "text": final_content_for_sms,
            "is_faq_answer": answered_as_faq_by_ai, 
            "ai_should_reply_directly_as_faq": answered_as_faq_by_ai 
        }

    async def analyze_customer_response(self, customer_id: int, message: str) -> dict:
        # Placeholder, as per your existing code
        logger.warning("AI_SERVICE: analyze_customer_response not fully implemented yet.")
        return {"sentiment": "unknown", "next_step": "review_manually"}