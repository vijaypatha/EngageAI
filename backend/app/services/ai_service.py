# backend/app/services/ai_service.py
import re
import json
import logging
from datetime import datetime, timedelta, time
from typing import Dict, Any # Ensure Dict and Any are imported
import pytz

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import openai

# Assuming Customer, BusinessProfile, RoadmapMessage are correctly imported from app.models
from app.models import Customer, BusinessProfile, RoadmapMessage, MessageStatusEnum # Ensure MessageStatusEnum is imported
from app.schemas import RoadmapGenerate, RoadmapResponse, RoadmapMessageResponse
from app.config import settings
from app.services.style_service import StyleService
from app.timezone_utils import get_business_timezone

logger = logging.getLogger(__name__)

# parse_customer_notes function remains unchanged
def parse_customer_notes(notes: str) -> dict:
    # ... (existing code from your file)
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

# parse_business_profile_for_campaigns function remains unchanged
def parse_business_profile_for_campaigns(business_goal: str, primary_services: str) -> dict:
    # ... (existing code from your file)
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
                "relationship_notes": customer.interaction_history,
                "parsed_notes": customer_notes_info
            }
            current_date_str = datetime.utcnow().strftime("%Y-%m-%d")

            # --- MODIFICATION 1: Strengthen AI Prompt for JSON structure ---
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
                        # MODIFIED TECHNICAL REQUIREMENTS SECTION
                        "TECHNICAL REQUIREMENTS:\n"
                        "1. Output ONLY the specified JSON object with a top-level key 'messages'.\n"
                        "2. The 'messages' key must contain a list of message objects.\n"
                        "3. Each message object in the list MUST contain the following keys:\n"
                        "   - 'days_from_today': (Integer) Calculated from 'Current Date'.\n"
                        "   - 'sms_text': (String) The actual SMS message content. THIS KEY MUST BE NAMED 'sms_text'.\n"
                        "   - 'purpose': (String) Descriptive purpose of the message.\n"
                        "   - OPTIONALLY, you may include a 'date' (String, YYYY-MM-DD format) for the target send date for clarity, but 'days_from_today' is primary for calculation.\n"
                        "4. Keep the 'sms_text' under 160 characters.\n"
                        "5. End 'sms_text' with the signature: '- {representative_name} from {business_name}'.\n"
                        "6. Base 'days_from_today' calculations on the 'Current Date': {current_date_str}.\n\n"
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

Output ONLY the JSON object with the 'messages' array. Each object within the 'messages' array MUST strictly contain the keys: 'days_from_today', 'sms_text' (for the message content), and 'purpose'. An optional 'date' key is also acceptable.
"""
                }
            ]
            # --- END OF PROMPT MODIFICATION ---
            
            logger.info(f"ℹ️ Sending request to OpenAI for customer {data.customer_id}, business {data.business_id}")
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
                     if ai_message_list is None and isinstance(ai_response.get("message"), str): # Your existing fallback
                         logger.warning("AI returned a single message object instead of a list. Wrapping it.")
                         ai_message_list = [ai_response] # This structure would need careful handling if it's a single message item
                     else:
                         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON format ('messages' key not a list or missing)")
            except json.JSONDecodeError as decode_error:
                 logger.error(f"❌ Failed to parse OpenAI response JSON: {decode_error} - Content: {content}")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON content")
            except Exception as parse_exc:
                 logger.error(f"❌ Error processing AI response structure: {parse_exc}")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error processing AI response: {parse_exc}")

            logger.info(f"✅ Attempting to parse {len(ai_message_list)} messages from AI.") # Changed log message

            roadmap_drafts_for_response = []
            business_tz_str = business.timezone or "UTC"
            business_tz = get_business_timezone(business_tz_str)
            logger.info(f"ℹ️ Processing {len(ai_message_list)} DRAFT messages using Business Timezone: {business_tz_str}")
            
            successful_parses = 0 # Counter for successful parses

            for idx, msg_data in enumerate(ai_message_list):
                if not isinstance(msg_data, dict): # Basic check if item is a dict
                    logger.warning(f"⚠️ Skipping invalid draft message item at index {idx} (not a dict): {msg_data}")
                    continue

                # --- MODIFICATION 2: Robust key checking for message text ---
                message_text_from_ai = None
                # Prioritize the explicitly requested 'sms_text', then fall back to others
                possible_text_keys = ["sms_text", "message", "content", "text"] 
                
                for key_to_try in possible_text_keys:
                    if key_to_try in msg_data and isinstance(msg_data[key_to_try], str):
                        message_text_from_ai = msg_data[key_to_try]
                        logger.debug(f"Found message text for draft {idx+1} using key '{key_to_try}'.")
                        break 
                
                required_keys = ["days_from_today", "purpose"]
                all_required_present = all(k in msg_data for k in required_keys)

                if not (all_required_present and message_text_from_ai is not None):
                    logger.warning(f"⚠️ Skipping invalid draft message item at index {idx} (missing essential fields or text key like 'sms_text', 'message', or 'content'): {msg_data}")
                    continue
                # --- END OF ROBUST KEY CHECKING ---

                try:
                    days_from_today = int(msg_data.get("days_from_today"))
                    if days_from_today < 0:
                         logger.warning(f"⚠️ AI returned negative days_from_today ({days_from_today}) for draft {idx+1}, using 0 instead.")
                         days_from_today = 0
                    target_date_utc = (datetime.utcnow() + timedelta(days=days_from_today)).date()
                    target_local_time = time(10, 0, 0) 
                    naive_local_dt = datetime.combine(target_date_utc, target_local_time)
                    localized_dt = business_tz.localize(naive_local_dt)
                    scheduled_time_utc = localized_dt.astimezone(pytz.UTC)
                    logger.debug(f"  Draft {idx+1}: days={days_from_today} -> ScheduledUTC={scheduled_time_utc}")
                except (ValueError, TypeError, KeyError) as e:
                    logger.error(f"❌ Error calculating scheduled time for draft (days_from_today='{msg_data.get('days_from_today')}', index={idx}): {e}. Falling back.")
                    # Fallback scheduling: Use UTC now + days_from_today at 10:00 UTC to avoid timezone complexities on error
                    base_time = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=pytz.UTC)
                    fallback_days = 0
                    try:
                        fallback_days = int(msg_data.get("days_from_today", idx + 1)) # default to index if key missing
                        if fallback_days < 0: fallback_days = 0
                    except ValueError:
                        logger.warning(f"Could not parse days_from_today for fallback, using index {idx+1}")
                        fallback_days = idx + 1 # Use index as absolute last resort
                    scheduled_time_utc = base_time + timedelta(days=fallback_days)
                
                final_message_content = message_text_from_ai[:160] # Use the robustly extracted text

                roadmap_draft = RoadmapMessage(
                    customer_id=customer.id,
                    business_id=business.id,
                    smsContent=final_message_content, # Ensure this uses the extracted text
                    smsTiming=f"{days_from_today} days from today",
                    send_datetime_utc=scheduled_time_utc,
                    status=MessageStatusEnum.DRAFT.value, # Use the enum value
                    relevance=str(msg_data.get("purpose", "Customer engagement")),
                    message_id=None
                )
                self.db.add(roadmap_draft)
                try:
                    self.db.flush() # Get ID for logging
                    self.db.refresh(roadmap_draft) # Ensure all fields are up-to-date from DB defaults if any
                except Exception as rm_flush_exc:
                     self.db.rollback()
                     logger.exception(f"❌ DB Error flushing roadmap draft for msg_data='{msg_data}': {rm_flush_exc}")
                     # Continue to next message rather than failing the whole batch
                     continue 
                
                try:
                    response_draft_model = RoadmapMessageResponse.model_validate(roadmap_draft)
                    roadmap_drafts_for_response.append(response_draft_model)
                    successful_parses += 1 # Increment successful parse counter
                except Exception as validation_error: # Should be rare if model/schema align
                     logger.error(f"❌ Failed to validate RoadmapMessageResponse Pydantic model for draft ID {roadmap_draft.id}: {validation_error}")
                     # Don't add this one to the response, already logged the error.
            
            # Commit outside the loop after processing all messages
            if successful_parses > 0:
                try:
                    self.db.commit()
                    logger.info(f"✅ Successfully committed {successful_parses} roadmap DRAFTS in DB for customer {data.customer_id}.")
                except Exception as commit_exc:
                    self.db.rollback()
                    logger.exception(f"❌ DB Error committing roadmap drafts for customer {data.customer_id}: {commit_exc}")
                    # Even if commit fails, some drafts might have been added to roadmap_drafts_for_response (if no Pydantic error)
                    # but they won't be in the DB. Clear the response list.
                    roadmap_drafts_for_response = [] 
                    successful_parses = 0
                    # Re-raise or return an error response
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save roadmap drafts to database.")
            elif len(ai_message_list) > 0 and successful_parses == 0:
                # If there were messages but none could be parsed/saved, it's a parsing failure for the batch
                logger.warning(f"⚠️ No AI messages could be processed into roadmap drafts for customer {data.customer_id}.")
                # No commit needed as nothing was successfully prepared to this stage.
            else: # No AI messages to process
                logger.info(f"ℹ️ No AI messages provided to process for customer {data.customer_id}.")


            return RoadmapResponse(
                status="success",
                message=f"Roadmap drafts generation processed. Successfully created {successful_parses} drafts." if successful_parses > 0 or len(ai_message_list) == 0 else "Roadmap drafts generation processed, but no messages could be saved.",
                roadmap=roadmap_drafts_for_response,
                total_messages=successful_parses, # Reflects only successfully created and validated drafts
                customer_info=customer_context,
                business_info=business_context
            )
        except HTTPException as http_exc: # Re-raise known HTTPExceptions
            logger.error(f"HTTP Error generating roadmap for customer {data.customer_id}: {http_exc.status_code} - {http_exc.detail}", exc_info=False) # exc_info=False if detail is enough
            self.db.rollback() # Ensure rollback
            raise http_exc
        except openai.OpenAIError as ai_error: # Specific OpenAI errors
             self.db.rollback()
             logger.error(f"❌ OpenAI API Error generating roadmap for customer {data.customer_id}: {ai_error}")
             raise HTTPException(
                 status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                 detail=f"AI service error: {str(ai_error)}"
             )
        except Exception as e: # Catch-all for other unexpected errors
            self.db.rollback()
            logger.exception(f"❌ Unexpected Error generating roadmap for customer {data.customer_id}: {str(e)}") # Use logger.exception to include traceback
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An internal server error occurred while generating the roadmap drafts."
            )

    async def generate_sms_response(self, message: str, customer_id: int, business_id: int) -> Dict[str, Any]:
        # ... (Your existing generate_sms_response method remains unchanged by this request) ...
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
        
        user_notes_for_reply = customer.interaction_history or ""
        reply_language_instruction = ""
        if "spanish" in user_notes_for_reply.lower() or "español" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Spanish."
        elif "chinese" in user_notes_for_reply.lower() or "mandarin" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Chinese (Mandarin)."
        elif "portuguese" in user_notes_for_reply.lower() or "português" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Portuguese."
        elif "telugu" in user_notes_for_reply.lower() or "telugu" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Telugu."
        else:
            reply_language_instruction = "Please reply in English."

        faq_context_str = ""
        is_faq_type_request = False 
        faq_data_dict = {} 

        if business.enable_ai_faq_auto_reply and business.structured_faq_data: 
            logger.info(f"FAQ Auto-Reply logic active for Business ID {business.id}.") 
            faq_data_dict = business.structured_faq_data 
            
            lower_message = message.lower()
            address_keywords = ["address", "location", "where are you", "where is your office", "directions"]
            hours_keywords = ["hours", "open", "close", "operating hours", "when are you open"]
            website_keywords = ["website", "site", "url", "web page"]

            if any(keyword in lower_message for keyword in address_keywords):
                is_faq_type_request = True
                faq_context_str += f"\n- The business address is: {faq_data_dict.get('address', 'Not specified')}"
            if any(keyword in lower_message for keyword in hours_keywords):
                is_faq_type_request = True
                faq_context_str += f"\n- Operating hours: {faq_data_dict.get('operating_hours', 'Not specified')}"
            if any(keyword in lower_message for keyword in website_keywords):
                is_faq_type_request = True
                faq_context_str += f"\n- Website: {faq_data_dict.get('website', 'Not specified')}"
            
            custom_faqs = faq_data_dict.get('custom_faqs', [])
            if custom_faqs:
                custom_faq_match_found = False
                temp_custom_faq_context = "\n\nCustom Q&As available:"
                for faq_item in custom_faqs:
                    question_text = faq_item.get('question', '').lower()
                    if question_text and (question_text in lower_message or lower_message in question_text or any(keyword in lower_message for keyword in question_text.split() if len(keyword)>3)): 
                         is_faq_type_request = True 
                         custom_faq_match_found = True
                         temp_custom_faq_context += f"\n  - Q: {faq_item.get('question')}\n    A: {faq_item.get('answer')}"
                if custom_faq_match_found:
                    faq_context_str += temp_custom_faq_context
            
            if is_faq_type_request: 
                logger.info(f"Potential FAQ request detected. Context prepared for AI: {faq_context_str}")
            elif business.enable_ai_faq_auto_reply : 
                logger.info("Message not a direct FAQ type or no specific keywords matched, but AI Autopilot is ON. Providing all FAQ data for general context to AI.")
                if faq_data_dict.get('address'): faq_context_str += f"\n- Business address: {faq_data_dict.get('address')}"
                if faq_data_dict.get('operating_hours'): faq_context_str += f"\n- Operating hours: {faq_data_dict.get('operating_hours')}"
                if faq_data_dict.get('website'): faq_context_str += f"\n- Website: {faq_data_dict.get('website')}"
                if custom_faqs:
                    faq_context_str += "\n\nOther potentially relevant Q&As (general context):" 
                    for faq_item in custom_faqs: faq_context_str += f"\n  - Q: {faq_item.get('question')} -> A: {faq_item.get('answer')}"

        prompt_parts = [
            f"You are a friendly assistant for {business.business_name}, a {business.industry} business.",
            f"The business owner is {rep_name} and prefers this tone and style (follow it closely):",
            json.dumps(style_guide, indent=2),
            f"\nThe customer is {customer.customer_name}. Previous interactions/notes: '{user_notes_for_reply}'.",
            f"\nThe customer just sent this message: \"{message}\"",
            reply_language_instruction 
        ]

        faq_marker = "##FAQ_ANSWERED##" 

        if business.enable_ai_faq_auto_reply and faq_context_str: 
            prompt_parts.append(f"\n\nIMPORTANT CONTEXTUAL BUSINESS INFORMATION (for FAQs if applicable):")
            prompt_parts.append(faq_context_str)
            prompt_parts.append(f"\nIf you use any of the above contextual business information to directly and completely answer the customer's question, append the exact marker '{faq_marker}' to the VERY END of your reply. Otherwise, do NOT append the marker.")
            prompt_parts.append("If you cannot directly answer with the provided FAQ information, have a natural, helpful conversation or indicate you will get assistance for their specific query. Do not makeup information not in the FAQ context.")
        
        prompt_parts.append(f"\n\nRESPONSE GUIDELINES: Draft a friendly, natural-sounding SMS reply. Keep it under 160 characters. Adhere to the owner's style. Sign off as \"- {rep_name}\".")
        if not (business.enable_ai_faq_auto_reply and is_faq_type_request): 
             prompt_parts.append("Avoid promotions unless directly asked or highly relevant to their query.")

        prompt = "\n".join(prompt_parts)
        logger.debug(f"generate_sms_response PROMPT for Business ID {business.id}:\n{prompt}")
        
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
            logger.info(f"AI indicated FAQ was answered (marker found). Business ID: {business.id}. Cleaned SMS: '{final_content_for_sms}'")
        else:
            logger.info(f"AI reply processed. Business ID: {business.id}. SMS: '{final_content_for_sms}'. FAQ Autopilot Engaged: {answered_as_faq_by_ai}")

        return {
            "text": final_content_for_sms,
            "is_faq_answer": answered_as_faq_by_ai, 
            "ai_should_reply_directly_as_faq": answered_as_faq_by_ai 
        }

    async def analyze_customer_response(self, customer_id: int, message: str) -> dict:
        logger.warning("analyze_customer_response not fully implemented yet.")
        return {"sentiment": "unknown", "next_step": "review_manually"}