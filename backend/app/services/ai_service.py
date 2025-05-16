# backend/app/services/ai_service.py
import re
import json
import logging
from datetime import datetime, timedelta, time
from typing import Dict, Any 
import pytz

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import openai

from app.models import Customer, BusinessProfile, RoadmapMessage, MessageStatusEnum 
from app.schemas import RoadmapGenerate, RoadmapResponse, RoadmapMessageResponse
from app.config import settings
from app.services.style_service import StyleService # Assuming this is the correct way to import
from app.timezone_utils import get_business_timezone # For timezone handling

logger = logging.getLogger(__name__)

# Helper function to parse notes for special dates (remains the same)
def parse_customer_notes(notes: str) -> dict:
    parsed_info = {}
    if not notes:
        return parsed_info
    
    notes_lower = notes.lower()
    
    # Birthday parsing logic (as provided by you)
    birthday_patterns = [
        r'(?:birthday|bday)\s*(?:is|on)?\s+([a-zA-Z]+)\s+(\d{1,2})(?:st|nd|rd|th)?', # Month Name DD
        r'(\d{1,2})/(\d{1,2})\s+birthday' # MM/DD birthday
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

                if month_str.isdigit(): # Case for MM/DD
                    month_num = int(month_str)
                else: # Case for Month Name
                    month_map = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                                 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
                    month_num = month_map.get(month_str[:3].lower()) # Ensure lowercase for map lookup

                if month_num and 1 <= month_num <= 12 and 1 <= day <= 31:
                    parsed_info['birthday_month'] = month_num
                    parsed_info['birthday_day'] = day
                    
                    today = datetime.utcnow().date() # Use UTC for consistent date comparison
                    current_year = today.year
                    try:
                        # Create birthday for current year to compare
                        next_birthday_dt = datetime(current_year, month_num, day)
                        next_birthday = next_birthday_dt.date()

                        if next_birthday < today: # If birthday already passed this year
                            next_birthday = datetime(current_year + 1, month_num, day).date()
                        
                        parsed_info['days_until_birthday'] = (next_birthday - today).days
                        found_birthday = True
                        break 
                    except ValueError:
                        # This can happen if, e.g., Feb 29 is parsed for a non-leap year.
                        logger.warning(f"Could not form a valid date for birthday {month_num}/{day} in year {current_year}. Storing raw parts.")
                        # Store raw parts for AI, maybe it can infer or it indicates bad data entry
                        parsed_info['birthday_details'] = f"Month {month_num}, Day {day} (unable to calculate days_until)"
                        found_birthday = True # Still consider it "found" to include in notes for AI
                        break
            except (ValueError, IndexError):
                 logger.warning(f"Could not parse birthday fragment: Month='{month_str}', Day='{day_str}'")
                 continue # Try next pattern
    
    if found_birthday:
        logger.info(f"Birthday parsed: {parsed_info}")
    else:
        logger.info("No explicit birthday found in notes.")

    # Example for holiday parsing - can be expanded
    # For now, this is simple keyword matching. A more robust solution might involve a date library or calendar checks.
    if "christmas" in notes_lower:
        parsed_info["mentions_christmas"] = True
    if "new year" in notes_lower:
        parsed_info["mentions_new_year"] = True
    if "july 4th" in notes_lower or "independence day" in notes_lower:
        parsed_info["mentions_july_4th"] = True
    if "thanksgiving" in notes_lower:
        parsed_info["mentions_thanksgiving"] = True
    # Add more common holidays or event keywords if needed

    logger.info(f"Final parsed customer notes for AI: {parsed_info}")
    return parsed_info

# Helper function to parse business profile for campaigns (remains the same)
def parse_business_profile_for_campaigns(business_goal: str, primary_services: str) -> dict:
    campaign_details = {
        "detected_sales_phrases": [],
        "discounts_mentioned": [],
        "product_focus_for_sales": [],
        "general_strategy": business_goal # Keep original goal text for AI
    }
    
    text_to_search = (business_goal.lower() if business_goal else "") + " " + \
                     (primary_services.lower() if primary_services else "")

    # Keywords that might indicate sales/promotions
    sales_keywords = ["sale", "sales", "discount", "offer", "promo", "promotion", "special", "deal", "save", "off"]
    for keyword in sales_keywords:
        if keyword in text_to_search:
            campaign_details["detected_sales_phrases"].append(keyword)

    # Look for percentage or dollar off discounts
    # Matches like "10% off", "20% discount", "$5 off", "save 15%"
    percentage_matches = re.findall(r'(\d{1,3}%?\s*(?:off|discount|saving[s]?)|save\s+\d{1,3}%|\$\d+\s*off)', text_to_search)
    if percentage_matches:
        campaign_details["discounts_mentioned"].extend([match.strip() for match in percentage_matches])

    # Look for product/service focus for sales
    # Matches like "sale on [product/service]", "offer for [product/service]"
    product_focus_matches = re.findall(
        r'(?:sale|discount|offer|promo(?:tion)?)s?[\s\w%-]*on\s+([\w\s\/]+?)(?:\s+for|\s+during|\s+on|\.|$)', 
        text_to_search
    )
    if product_focus_matches:
        campaign_details["product_focus_for_sales"].extend([p.strip() for p in product_focus_matches])

    # Set a flag if any sales-related info was found
    if campaign_details["detected_sales_phrases"] or \
       campaign_details["discounts_mentioned"] or \
       campaign_details["product_focus_for_sales"]:
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
        # Log entry into the function
        logger.info(f"AI_SERVICE: Starting roadmap generation for Customer ID: {data.customer_id}, Business ID: {data.business_id}")
        
        try:
            # Fetch customer and business details (existing logic)
            customer = self.db.query(Customer).filter(Customer.id == data.customer_id).first()
            if not customer:
                 logger.error(f"AI_SERVICE: Customer with ID {data.customer_id} not found.")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer with ID {data.customer_id} not found")
            
            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == data.business_id).first()
            if not business:
                 logger.error(f"AI_SERVICE: Business with ID {data.business_id} not found.")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with ID {data.business_id} not found")

            # Fetch style guide (existing logic)
            style_service = StyleService() # Ensure StyleService can be instantiated correctly
            class StyleWrapper:
                 def __init__(self, style_dict): self.style_analysis = style_dict or {} # Handle None
            
            # Use try-except for style guide fetching as it's an async call that might fail
            try:
                style_guide_raw = await style_service.get_style_guide(business.id, self.db)
                style = StyleWrapper(style_guide_raw)
            except Exception as sg_exc:
                logger.error(f"AI_SERVICE: Failed to fetch style guide for business {business.id}: {sg_exc}", exc_info=True)
                style = StyleWrapper(None) # Proceed with empty style guide if fetch fails
            
            style_guide = style.style_analysis if style and style.style_analysis else {}
            logger.debug(f"AI_SERVICE: Style guide loaded for business {business.id}: {json.dumps(style_guide, indent=2) if style_guide else 'No style guide found/used.'}")


            # Prepare business and customer context (existing logic)
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
            customer_notes_info = parse_customer_notes(customer.interaction_history)
            customer_context = {
                "name": customer.customer_name,
                "lifecycle_stage": customer.lifecycle_stage,
                "pain_points": customer.pain_points,
                "relationship_notes": customer.interaction_history,
                "parsed_notes": customer_notes_info,
                "customer_timezone": customer.timezone 
            }
            current_date_str = datetime.utcnow().strftime("%Y-%m-%d") # Current date in UTC

            # Log the prepared contexts
            logger.debug(f"AI_SERVICE: Business Context for Prompt: {json.dumps(business_context, indent=2)}")
            logger.debug(f"AI_SERVICE: Customer Context for Prompt: {json.dumps(customer_context, indent=2)}")
            logger.info(f"AI_SERVICE: Current UTC Date for AI Context: {current_date_str}")

            # --- Enhanced AI Prompt ---
            messages_for_openai = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert SMS engagement strategist for small businesses. Your goal is to create thoughtful, personalized SMS roadmaps that genuinely connect with customers and align with the business's objectives. You must strictly follow all instructions and use the provided data accurately.\n\n"
                        "CORE MISSION: Ensure every message is **temporally relevant** to its calculated send date (based on 'Current Date' + 'days_from_today') and contextually appropriate for the customer and business.\n\n"
                        "GENERAL PRINCIPLES:\n"
                        "1.  **Data-Driven Personalization:** The 'Customer Profile' (especially 'relationship_notes', 'pain_points', and 'parsed_notes') is paramount. Your messages MUST reflect this data. If 'relationship_notes' indicate a dislike (e.g., 'Doesn't Bike'), NEVER suggest that activity. If no specific interests are noted for general check-ins, keep messages broadly positive and supportive, related to the business's services without making assumptions.\n"
                        "2.  **Language Determination:** Carefully analyze 'Customer Profile -> relationship_notes' to determine if a preferred communication language other than English is explicitly stated or strongly implied. If a clear preference for a specific language is found, ALL generated SMS messages for this customer MUST be in that language. If no such preference is clear, default to English.\n"
                        "3.  **Business Goal & Campaign Alignment:** The 'Business Profile -> goal_text' and 'extracted_campaign_info' dictate the strategy. This includes message frequency, holiday messaging strategy (including any sales details from 'extracted_campaign_info'), and the overall purpose.\n"
                        "4.  **Event-Specific Messaging Rules & CRITICAL TEMPORAL CONTEXT:**\n"
                        "    * **Current Date for Context:** All message themes and content MUST be relevant to their calculated send date. The 'Current Date' is {current_date_str} (YYYY-MM-DD format, UTC). A message for 'Day 60' from this Current Date must be themed for approximately 60 days from now. For example, if Current Date is 2025-05-15, 'Day 60' is around mid-July 2025; the message theme should reflect summer, not winter or unrelated holidays.\n"
                        "    * **Special Dates (from `customer_context['parsed_notes']`):**\n"
                        "        * Use 'days_until_birthday' from `customer_context['parsed_notes']`. A message for this event MUST be themed as a birthday wish and scheduled accordingly (e.g., if 'days_until_birthday' is 30, set 'days_from_today' to 27-25 for a message 3-5 days before the birthday).\n"
                        "        * Other special dates mentioned in `customer_context['parsed_notes']` (like anniversaries or specific customer events) should also be used to craft relevant messages if they fall within the 6-9 month planning window.\n"
                        "    * **Holiday Messages (General US Holidays):**\n"
                        "        * Only generate messages for major US holidays (e.g., New Year's, July 4th, Thanksgiving, Christmas) IF their actual calendar date falls within the 6-9 month planning window calculated from the 'Current Date'.\n"
                        "        * The message content MUST be appropriate for that *specific holiday* and its timing. For example, a July 4th message should only be scheduled if July 4th is upcoming relative to the 'Current Date' + 'days_from_today'. DO NOT generate a July 4th themed message if its calculated send date is in September.\n"
                        "        * If 'Business Profile -> extracted_campaign_info -> has_sales_info' is true, try to incorporate sales details from 'discounts_mentioned' or 'product_focus_for_sales' into these specific holiday messages naturally. If general sales are indicated but specifics are missing for that holiday, use a placeholder like `[Check out our special holiday deals!]`. If 'has_sales_info' is false, holiday messages are for greetings ONLY.\n"
                        "5.  **Style Adherence:** Perfectly match the 'Business Owner Communication Style' details provided.\n"
                        "TECHNICAL REQUIREMENTS:\n"
                        "1. Output ONLY the specified JSON object with a top-level key 'messages'.\n"
                        "2. The 'messages' key must contain a list of 3 to 5 message objects.\n"
                        "3. Each message object in the list MUST contain the following keys:\n"
                        "   - 'days_from_today': (Integer) Calculated relative to 'Current Date'. This determines the send date. This value must be non-negative.\n"
                        "   - 'sms_text': (String) The actual SMS message content. The theme of this text MUST match the season and any events relevant to the calculated send date. THIS KEY MUST BE NAMED 'sms_text'.\n"
                        "   - 'purpose': (String) Descriptive purpose of the message (e.g., 'July 4th Greetings', 'Early Spring Check-in', 'Birthday Well-wishes').\n"
                        "4. Keep the 'sms_text' under 160 characters.\n"
                        "5. End 'sms_text' with the signature: '- {representative_name} from {business_name}'.\n\n"
                        "INTERPRETING 'Business Profile -> extracted_campaign_info':\n"
                        "- Use 'general_strategy' (the original business_goal text) for overall direction.\n"
                        "- If 'has_sales_info' is true, use 'discounts_mentioned' and 'product_focus_for_sales' to make holiday and promotional messages specific. If these details are vague in the extraction, create a compelling general sales message or use a placeholder for the owner to refine.\n"
                        "- Determine check-in frequency based on keywords like 'monthly' or 'quarterly' found in 'general_strategy'. Default to quarterly if unspecified. Ensure check-ins are seasonally appropriate for their calculated send date.\n"
                    ).format(representative_name=business_context['representative_name'], business_name=business_context['name'], current_date_str=current_date_str)
                },
                {
                    "role": "user",
                    "content": f"""
Current Date (UTC): {current_date_str}

Business Profile:
{json.dumps(business_context, indent=2)}

Customer Profile:
{json.dumps(customer_context, indent=2)} 

Business Owner Communication Style:
{json.dumps(style_guide, indent=2)}

---

TASK:
First, determine the customer's preferred communication language by carefully analyzing the 'Customer Profile -> relationship_notes'. If a specific language (e.g., Spanish, Chinese, Portuguese, French) is mentioned or strongly implied as their preference, use that language for all SMS messages you generate. If no preference is found, default to English.

Then, generate a personalized SMS engagement plan of 3 to 5 messages for the customer in the determined language for the next 6-9 months. This plan must strictly follow all system instructions, especially regarding **temporal relevance** and style.

The plan should thoughtfully integrate:
A.  **Regular Check-ins:** At the frequency indicated by 'Business Profile -> extracted_campaign_info -> general_strategy' or default to quarterly. The content of these check-ins MUST be seasonally and thematically appropriate for their calculated send date relative to the 'Current Date'. For example, if a check-in's 'days_from_today' results in a January send date (and Current Date is in May), its theme should reflect winter, not spring.
B.  **Birthday Message:** If 'days_until_birthday' is available in `customer_context['parsed_notes']`, schedule one message 3-5 days prior to that birthday. The message content must be a simple birthday wish. 'days_from_today' for this message should be `parsed_notes['days_until_birthday'] - (3 to 5)`.
C.  **Holiday Messages:** Only for relevant major US holidays IF their actual calendar date falls within the 6-9 month planning window (calculated from 'Current Date' + 'days_from_today'). The content MUST be appropriate for that *specific holiday* and its timing. If 'Business Profile -> extracted_campaign_info -> has_sales_info' is true, integrate sales details. Do NOT generate holiday messages for incorrect seasons or if no relevant holiday is upcoming in the plan timeframe.
D.  **Content Sensitivity:** Ensure all messages are sensitive to 'Customer Profile'.

CRITICAL: For each message, 'days_from_today' determines its send date. The `sms_text` MUST be thematically relevant to this calculated send date.
The "purpose" field should be descriptive and reflect the message's theme and timing.

Output ONLY the JSON object with the 'messages' array. Each object within the 'messages' array MUST strictly contain the keys: 'days_from_today', 'sms_text', and 'purpose'.
"""
                }
            ]
            # --- End of Enhanced AI Prompt ---
            
            logger.info(f"AI_SERVICE: Sending request to OpenAI for customer {data.customer_id}, business {data.business_id} with detailed prompt.")
            # Log the full prompt being sent to OpenAI for debugging
            # Be cautious with logging sensitive data in production
            # logger.debug(f"AI_SERVICE: Full prompt being sent to OpenAI: {json.dumps(messages_for_openai, indent=2)}")

            response = self.client.chat.completions.create(
                model="gpt-4o", # Ensure this model is suitable for complex instructions
                messages=messages_for_openai,
                response_format={"type": "json_object"} # Request JSON object output
            )

            content = response.choices[0].message.content
            logger.info(f"AI_SERVICE: OpenAI raw response content: {content[:500]}...") # Log a snippet

            # --- Robust JSON Parsing and Validation ---
            try:
                ai_response = json.loads(content)
                if not isinstance(ai_response, dict):
                    logger.error("AI_SERVICE: AI response is not a JSON object.")
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON format (not an object)")
                
                ai_message_list = ai_response.get("messages")
                if not isinstance(ai_message_list, list):
                    logger.error("AI_SERVICE: 'messages' key in AI response is not a list or is missing.")
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON format ('messages' key not a list or missing)")
            except json.JSONDecodeError as decode_error:
                 logger.error(f"AI_SERVICE: Failed to parse OpenAI response JSON: {decode_error}. Content: {content[:500]}...")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON content")
            except Exception as parse_exc: # Catch any other error during basic parsing
                 logger.error(f"AI_SERVICE: Error processing AI response structure: {parse_exc}. Content: {content[:500]}...")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error processing AI response: {parse_exc}")

            logger.info(f"AI_SERVICE: Successfully parsed AI JSON. Attempting to process {len(ai_message_list)} message items.")

            # --- Processing AI Messages and Storing in DB ---
            roadmap_drafts_for_response = []
            business_tz_str = business.timezone or "UTC" # Default to UTC if not set
            business_tz = get_business_timezone(business_tz_str) # Get pytz timezone object
            logger.info(f"AI_SERVICE: Processing {len(ai_message_list)} DRAFT messages using Business Timezone: {business_tz_str}")
            
            successful_parses = 0 

            for idx, msg_data in enumerate(ai_message_list):
                log_msg_prefix = f"AI_SERVICE: Draft Item {idx+1}/{len(ai_message_list)}"
                if not isinstance(msg_data, dict): 
                    logger.warning(f"{log_msg_prefix}: Skipping invalid item (not a dict): {str(msg_data)[:100]}...")
                    continue

                message_text_from_ai = None
                possible_text_keys = ["sms_text", "message", "content", "text"] # Common keys AI might use
                
                for key_to_try in possible_text_keys:
                    if key_to_try in msg_data and isinstance(msg_data[key_to_try], str):
                        message_text_from_ai = msg_data[key_to_try]
                        logger.debug(f"{log_msg_prefix}: Found message text using key '{key_to_try}'.")
                        break 
                
                required_keys = ["days_from_today", "purpose"]
                all_required_present = all(k in msg_data for k in required_keys)

                if not (all_required_present and message_text_from_ai is not None):
                    logger.warning(f"{log_msg_prefix}: Skipping item due to missing essential fields (days_from_today, purpose, or a text key like 'sms_text'). Data: {str(msg_data)[:100]}...")
                    continue
                
                # --- Date Calculation and Timezone Handling ---
                try:
                    days_offset = int(msg_data.get("days_from_today"))
                    if days_offset < 0: # Ensure non-negative offset
                         logger.warning(f"{log_msg_prefix}: AI returned negative days_from_today ({days_offset}), using 0 instead.")
                         days_offset = 0
                    
                    # Base date for calculation is the 'current_date_str' (which is UTC)
                    base_utc_date_for_calc = datetime.strptime(current_date_str, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
                    
                    # Add the offset to the UTC base date
                    target_utc_date_exact = base_utc_date_for_calc + timedelta(days=days_offset)
                    
                    # Default send time (e.g., 10:00 AM) in the business's local timezone
                    target_local_time_obj = time(10, 0, 0) 
                    
                    # Combine the target UTC date with the local business time, then localize to business timezone
                    naive_target_dt_in_business_tz = datetime.combine(target_utc_date_exact.date(), target_local_time_obj)
                    localized_target_dt_in_business_tz = business_tz.localize(naive_target_dt_in_business_tz)
                    
                    # Convert this localized target datetime to UTC for storage
                    scheduled_time_utc_final = localized_target_dt_in_business_tz.astimezone(pytz.UTC)

                    logger.debug(f"{log_msg_prefix}: DaysOffset={days_offset}, BaseUTC={base_utc_date_for_calc.isoformat()}, TargetDateFromBase={target_utc_date_exact.date()}, LocalTime={target_local_time_obj} in {business_tz_str} -> LocalizedDT={localized_target_dt_in_business_tz.isoformat()} -> FinalScheduledUTC={scheduled_time_utc_final.isoformat()}")

                except (ValueError, TypeError, KeyError) as e:
                    logger.error(f"{log_msg_prefix}: Error calculating scheduled time (days_from_today='{msg_data.get('days_from_today')}'): {e}. Applying fallback.", exc_info=True)
                    # Fallback: schedule for 'idx + 1' days from now (UTC), at 10:00 UTC
                    base_fallback_time = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=pytz.UTC)
                    try:
                        fallback_offset = int(msg_data.get("days_from_today", idx + 1)) # Try to use AI's offset, else index
                        if fallback_offset < 0: fallback_offset = idx + 1 # Ensure non-negative
                    except ValueError:
                        fallback_offset = idx + 1
                    scheduled_time_utc_final = base_fallback_time + timedelta(days=fallback_offset)
                    logger.warning(f"{log_msg_prefix}: Fallback scheduled time set to: {scheduled_time_utc_final.isoformat()}")

                final_message_content_for_db = message_text_from_ai[:1600] # Truncate if necessary (DB limit)

                roadmap_draft = RoadmapMessage(
                    customer_id=customer.id,
                    business_id=business.id,
                    smsContent=final_message_content_for_db, 
                    smsTiming=f"{days_offset} days from today", # Original relative timing from AI
                    send_datetime_utc=scheduled_time_utc_final, # Store the calculated UTC time
                    status=MessageStatusEnum.DRAFT.value, 
                    relevance=str(msg_data.get("purpose", "Customer engagement")), # Purpose from AI
                    message_id=None # Will be null for drafts not yet linked to Message table
                )
                self.db.add(roadmap_draft)
                try:
                    self.db.flush() 
                    self.db.refresh(roadmap_draft) 
                    logger.debug(f"{log_msg_prefix}: Successfully flushed RoadmapMessage draft ID {roadmap_draft.id}.")
                except Exception as rm_flush_exc:
                     self.db.rollback() # Rollback this specific add
                     logger.error(f"{log_msg_prefix}: DB Error flushing roadmap draft for item: {str(msg_data)[:100]}... Error: {rm_flush_exc}", exc_info=True)
                     continue # Skip to the next message item from AI
                
                try:
                    # Validate against Pydantic model before adding to response list
                    response_draft_model = RoadmapMessageResponse.from_orm(roadmap_draft)
                    roadmap_drafts_for_response.append(response_draft_model)
                    successful_parses += 1 
                    logger.debug(f"{log_msg_prefix}: Validated and added draft ID {roadmap_draft.id} to response list.")
                except Exception as validation_error: 
                     logger.error(f"{log_msg_prefix}: Failed to validate Pydantic model for draft ID {roadmap_draft.id}: {validation_error}", exc_info=True)
                     # Do not add to response list if validation fails. The DB record might still exist if flush succeeded.
            
            # --- Commit all successfully processed drafts ---
            if successful_parses > 0:
                try:
                    self.db.commit()
                    logger.info(f"AI_SERVICE: Successfully committed {successful_parses} roadmap DRAFTS in DB for customer {data.customer_id}.")
                except Exception as commit_exc:
                    self.db.rollback()
                    logger.error(f"AI_SERVICE: DB Error committing roadmap drafts for customer {data.customer_id}: {commit_exc}", exc_info=True)
                    # If commit fails, the drafts added to roadmap_drafts_for_response might not actually be in the DB.
                    # It's safer to clear the response list or re-fetch, or indicate an error state.
                    roadmap_drafts_for_response = [] 
                    successful_parses = 0 # Reset count as commit failed
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save roadmap drafts to database after processing.")
            elif len(ai_message_list) > 0 and successful_parses == 0:
                logger.warning(f"AI_SERVICE: No AI messages could be successfully processed into roadmap drafts for customer {data.customer_id}.")
            else: 
                logger.info(f"AI_SERVICE: No AI messages were provided or found in the AI response for customer {data.customer_id}.")

            # --- Return the final response ---
            final_status_message = f"Roadmap drafts generation processed. Successfully created and saved {successful_parses} drafts." \
                                   if successful_parses > 0 or len(ai_message_list) == 0 \
                                   else "Roadmap drafts generation processed, but no messages could be saved due to processing errors."

            return RoadmapResponse(
                status="success" if successful_parses > 0 or len(ai_message_list) == 0 else "partial_error",
                message=final_status_message,
                roadmap=roadmap_drafts_for_response,
                total_messages=successful_parses, # Reflects only successfully created and validated drafts
                customer_info=customer_context,
                business_info=business_context
            )
        
        # --- Exception Handling ---
        except HTTPException as http_exc: 
            logger.error(f"AI_SERVICE: HTTPException during roadmap generation for customer {data.customer_id}: {http_exc.status_code} - {http_exc.detail}", exc_info=False)
            if self.db.is_active: self.db.rollback() 
            raise http_exc
        except openai.OpenAIError as ai_error: 
             if self.db.is_active: self.db.rollback()
             logger.error(f"AI_SERVICE: OpenAI API Error generating roadmap for customer {data.customer_id}: {ai_error}", exc_info=True)
             raise HTTPException(
                 status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                 detail=f"AI service error: {str(ai_error)}"
             )
        except Exception as e: 
            if self.db.is_active: self.db.rollback()
            logger.exception(f"AI_SERVICE: Unexpected Error generating roadmap for customer {data.customer_id}: {str(e)}") 
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An internal server error occurred while generating the roadmap drafts: {str(e)}"
            )

    async def generate_sms_response(self, message: str, customer_id: int, business_id: int) -> Dict[str, Any]:
        # This method is for generating immediate replies, not roadmap planning.
        # The temporal context here would be "now" relative to the customer's message.
        # No changes requested for this method in the current user prompt.
        # Ensure its prompt logic is sound for its specific purpose if it involves future dates (unlikely for direct replies).
        # ... (existing code for generate_sms_response) ...
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
        class StyleWrapper:
            def __init__(self, style_dict): self.style_analysis = style_dict or {}
        
        try:
            style_guide_raw = await style_service.get_style_guide(business.id, self.db)
            style = StyleWrapper(style_guide_raw)
        except Exception as sg_exc:
            logger.error(f"AI_SERVICE: Failed to fetch style guide for business {business.id} during SMS response: {sg_exc}", exc_info=True)
            style = StyleWrapper(None)
        
        style_guide = style.style_analysis if style and style.style_analysis else {}
        logger.debug(f"AI_SERVICE: Style guide for SMS response: {json.dumps(style_guide, indent=2) if style_guide else 'No style guide.'}")

        rep_name = business.representative_name or business.business_name
        
        user_notes_for_reply = customer.interaction_history or ""
        # ... (rest of your language and FAQ detection logic for generate_sms_response) ...
        reply_language_instruction = ""
        if "spanish" in user_notes_for_reply.lower() or "español" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Spanish."
        elif "chinese" in user_notes_for_reply.lower() or "mandarin" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Chinese (Mandarin)."
        elif "portuguese" in user_notes_for_reply.lower() or "português" in user_notes_for_reply.lower():
            reply_language_instruction = "Please reply in Portuguese."
        elif "telugu" in user_notes_for_reply.lower(): # Corrected "telugu" to lowercase
            reply_language_instruction = "Please reply in Telugu."
        else:
            reply_language_instruction = "Please reply in English."

        faq_context_str = ""
        is_faq_type_request = False 
        faq_data_dict = {} 

        if business.enable_ai_faq_auto_reply and business.structured_faq_data: 
            logger.info(f"AI_SERVICE: FAQ Auto-Reply logic active for Business ID {business.id} during SMS response.") 
            faq_data_dict = business.structured_faq_data # This should already be a dict
            
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
            if custom_faqs and isinstance(custom_faqs, list): # Ensure it's a list
                custom_faq_match_found = False
                temp_custom_faq_context = "\n\nCustom Q&As available:"
                for faq_item_any in custom_faqs: # Iterate over potentially mixed-type list
                    if isinstance(faq_item_any, dict): # Process only if item is a dict
                        faq_item = faq_item_any # Now it's a dict
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

        faq_marker = "##FAQ_ANSWERED_FOR_DIRECT_REPLY##" # Use a distinct marker for direct replies

        if business.enable_ai_faq_auto_reply and faq_context_str: 
            prompt_parts.append(f"\n\nIMPORTANT CONTEXTUAL BUSINESS INFORMATION (for FAQs if applicable):")
            prompt_parts.append(faq_context_str)
            prompt_parts.append(f"\nIf you use any of the above contextual business information to directly and completely answer the customer's question, append the exact marker '{faq_marker}' to the VERY END of your reply. Otherwise, do NOT append the marker.")
            prompt_parts.append("If you cannot directly answer with the provided FAQ information, have a natural, helpful conversation or indicate you will get assistance for their specific query. Do not makeup information not in the FAQ context.")
        
        prompt_parts.append(f"\n\nRESPONSE GUIDELINES: Draft a friendly, natural-sounding SMS reply. Keep it under 160 characters. Adhere to the owner's style. Sign off as \"- {rep_name}\".")
        if not (business.enable_ai_faq_auto_reply and is_faq_type_request): # Only add this if NOT an FAQ-type request where autopilot is on
             prompt_parts.append("Avoid promotions unless directly asked or highly relevant to their query.")

        prompt = "\n".join(prompt_parts)
        logger.debug(f"AI_SERVICE: generate_sms_response PROMPT for Business ID {business.id}:\n{prompt[:1000]}...") # Log snippet
        
        response = self.client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "system", "content": "You craft helpful and friendly SMS replies based on provided context and instructions."},
                      {"role": "user", "content": prompt}],
            max_tokens=100 # For SMS, keep it concise
        )
        
        raw_generated_content = response.choices[0].message.content.strip()
        
        answered_as_faq_by_ai = False 
        final_content_for_sms = raw_generated_content

        # Check for the distinct FAQ marker for direct replies
        if business.enable_ai_faq_auto_reply and raw_generated_content.endswith(faq_marker): 
            answered_as_faq_by_ai = True
            final_content_for_sms = raw_generated_content[:-len(faq_marker)].strip() 
            logger.info(f"AI_SERVICE: AI indicated FAQ was answered for direct reply (marker found). Business ID: {business.id}. Cleaned SMS: '{final_content_for_sms}'")
        else:
            logger.info(f"AI_SERVICE: AI direct reply processed. Business ID: {business.id}. SMS: '{final_content_for_sms}'. FAQ Autopilot Engaged for Direct Reply: {answered_as_faq_by_ai}")

        return {
            "text": final_content_for_sms,
            "is_faq_answer": answered_as_faq_by_ai, # This flag indicates if the content came from FAQ data
            "ai_should_reply_directly_as_faq": answered_as_faq_by_ai # This flag indicates AI's confidence to auto-reply using FAQ
        }


    async def analyze_customer_response(self, customer_id: int, message: str) -> dict:
        logger.warning("AI_SERVICE: analyze_customer_response not fully implemented yet.")
        # Placeholder implementation
        return {"sentiment": "unknown", "next_step": "review_manually"}