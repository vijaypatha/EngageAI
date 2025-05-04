# backend/app/services/ai_service.py
import re
import json
import logging
from datetime import datetime, timedelta, time
import pytz  # Add this import

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import openai

# Import necessary components from your application
from app.models import Customer, BusinessProfile, RoadmapMessage
from app.schemas import RoadmapGenerate, RoadmapResponse, RoadmapMessageResponse
from app.config import settings
from app.services.style_service import StyleService # Assuming this import is correct
from app.timezone_utils import get_business_timezone # Add this import

logger = logging.getLogger(__name__)

# --- Helper Function for Parsing Notes ---
def parse_customer_notes(notes: str) -> dict:
    """
    Parses customer interaction history notes for key information like birthday.
    """
    parsed_info = {}
    if not notes:
        return parsed_info

    notes_lower = notes.lower()

    # Simple Birthday Parsing (Example: "Birthday June 8", "bday is mar 15")
    # Allows for variations like 'birthday', 'bday', 'is', 'on'
    birthday_patterns = [
        r'(?:birthday|bday)\s*(?:is|on)?\s+([a-zA-Z]+)\s+(\d{1,2})(?:st|nd|rd|th)?', # Month Day
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
                if month_str.isdigit(): # Handle MM/DD format
                    month_num = int(month_str)
                else: # Handle Month name format
                    month_map = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                                 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
                    month_num = month_map.get(month_str[:3]) # Match first 3 letters

                if month_num and 1 <= month_num <= 12 and 1 <= day <= 31:
                    parsed_info['birthday_month'] = month_num
                    parsed_info['birthday_day'] = day
                    
                    # Calculate approximate days until next birthday
                    today = datetime.utcnow().date()
                    current_year = today.year
                    try:
                        # Check if the date is valid for the year
                        next_birthday_dt = datetime(current_year, month_num, day) 
                        next_birthday = next_birthday_dt.date()
                        if next_birthday < today:
                            # If past, check next year (handle leap year potential for Feb 29)
                            next_birthday = datetime(current_year + 1, month_num, day).date() 
                        parsed_info['days_until_birthday'] = (next_birthday - today).days
                        found_birthday = True
                        break # Stop after finding a valid birthday
                    except ValueError:
                        # Handle invalid date combinations (e.g., Feb 30) or leap year issues simply
                        logger.warning(f"Could not calculate days for birthday {month_num}/{day}. Date might be invalid.")
                        parsed_info['birthday_details'] = f"Month {month_num}, Day {day} (could not validate precisely)"
                        found_birthday = True
                        break # Stop after finding a potential birthday date

            except (ValueError, IndexError):
                 logger.warning(f"Could not parse birthday fragment: Month='{month_str}', Day='{day_str}'")
                 continue # Try next pattern if parsing fails

    # Add more parsing logic here for other keywords if needed...
    # Example:
    # if "doesn't like calls" in notes_lower:
    #    parsed_info['preferences'] = parsed_info.get('preferences', []) + ['avoids calls']

    return parsed_info


class AIService:
    def __init__(self, db: Session):
        self.db = db
        if not settings.OPENAI_API_KEY:
            logger.error("❌ OPENAI_API_KEY not configured in settings.")
            raise ValueError("OpenAI API Key is not configured.")
        self.client = openai.Client(api_key=settings.OPENAI_API_KEY)

    async def generate_roadmap(self, data: RoadmapGenerate) -> RoadmapResponse:
        """
        Generates a DRAFT roadmap of messages (stored in roadmap_messages)
        for a customer using AI, incorporating better context and timing.
        """
        try:
            # --- Get customer and business info ---
            customer = self.db.query(Customer).filter(Customer.id == data.customer_id).first()
            if not customer:
                 logger.warning(f"Customer not found for ID: {data.customer_id}")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer with ID {data.customer_id} not found")
            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == data.business_id).first()
            if not business:
                 logger.warning(f"Business not found for ID: {data.business_id}")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with ID {data.business_id} not found")

            # --- Get Style Guide ---
            style_service = StyleService()
            # Wrap the dict into an object safely
            class StyleWrapper:
                 def __init__(self, style_dict):
                    self.style_analysis = style_dict or {}
            style = StyleWrapper(await style_service.get_style_guide(business.id, self.db))
            style_guide = style.style_analysis if style and style.style_analysis else {}

            # --- Prepare Enhanced Context ---
            business_context = {
                "name": business.business_name,
                "industry": business.industry,
                "goal": business.business_goal,
                "services": business.primary_services,
                "representative_name": business.representative_name or business.business_name # Fallback for rep name
            }
            
            # Parse notes for specific details
            customer_notes_info = parse_customer_notes(customer.interaction_history)
            
            customer_context = {
                "name": customer.customer_name,
                "lifecycle_stage": customer.lifecycle_stage,
                "pain_points": customer.pain_points,
                "relationship_notes": customer.interaction_history,
                "parsed_notes": customer_notes_info # Include parsed info
            }

            preferred_language = "Spanish" if "spanish" in (customer.interaction_history or "").lower() else "English"
            current_date_str = datetime.utcnow().strftime("%Y-%m-%d") # Add current date

            # --- Build Improved OpenAI Prompt ---
            messages_for_openai = [
                {
                    "role": "system",
                    "content": (
                        "You are a thoughtful communication assistant for small businesses, crafting personalized SMS messages to build genuine customer relationships. Focus on warmth, sincerity, and matching the business owner's unique style.\n\n"
                        "CRITICAL INSTRUCTIONS:\n"
                        "1.  **Prioritize Customer Context:** Strictly adhere to the Customer Profile details, especially 'pain_points', 'relationship_notes', and 'parsed_notes'. NEVER suggest activities the customer dislikes or doesn't participate in (e.g., if notes say 'Doesn't Bike', do not mention biking). Use the 'parsed_notes' for specific dates like birthdays.\n"
                        "2.  **Respect Events:** Birthday and Holiday messages are for well-wishes ONLY. No promotions or sales pitches on these occasions.\n"
                        "3.  **Business Goals:** For regular check-ins, align the message purpose with the 'Business Profile -> goal'. If the goal involves growth, a gentle reminder of services is okay ONLY in non-event messages.\n"
                        "4.  **Style Matching:** Accurately replicate the 'Business Owner Communication Style' provided.\n"
                        "5.  **Signature:** ALWAYS end messages with '- {representative_name} from {business_name}'.\n"
                        "6.  **Conciseness:** Keep SMS under 160 characters.\n"
                        "7.  **Timing Calculation:** Calculate 'days_from_today' based on the 'Current Date' provided ({current_date_str}) and the target event dates (using 'parsed_notes' for birthday, standard US holidays, and quarterly intervals). Schedule birthday messages 3-5 days *before* the actual birthday. Schedule holiday messages 1-3 days before the holiday. Schedule quarterly check-ins approximately every 90 days from the current date.\n"
                        "8.  **Output Format:** Respond ONLY with a valid JSON object: `{{\"messages\": [...]}}`. Each object in the 'messages' array must have keys: 'message' (string), 'days_from_today' (integer), 'purpose' (string)."
                    ).format(representative_name=business_context['representative_name'], business_name=business_context['name'], current_date_str=current_date_str) # Pre-format system message if needed
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

Generate a personalized SMS engagement plan for the customer covering approximately the next 6 months.

The plan MUST include:
- Messages based on the 'Customer Profile' (paying close attention to notes/pain points) and 'Business Profile -> goal'.
- A birthday message IF 'parsed_notes' contains birthday info, scheduled 3-5 days *before* the birthday.
- Messages for major US holidays (e.g., Thanksgiving, Christmas, New Year's Day) IF they fall within the next 6 months, scheduled 1-3 days before the holiday.
- Quarterly check-in messages (approximately every 90 days from the current date).

Calculate the 'days_from_today' for each message accurately based on the '{current_date_str}' and the event date.

Output ONLY the JSON object.
"""
                }
            ]
            
            # --- Call OpenAI ---
            logger.info(f"ℹ️ Sending request to OpenAI for customer {data.customer_id}, business {data.business_id}")
            # Log the prompt being sent (optional, can be verbose)
            # logger.debug(f"🧠 OpenAI Prompt: {json.dumps(messages_for_openai, indent=2)}")
            response = self.client.chat.completions.create(
                model="gpt-4o", # Or your preferred model
                messages=messages_for_openai,
                response_format={"type": "json_object"}
            )

            # --- Parse AI Response ---
            content = response.choices[0].message.content
            logger.info("🧠 OpenAI raw response: %s", content)
            try:
                ai_response = json.loads(content)
                if not isinstance(ai_response, dict):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON format (not an object)")
                ai_message_list = ai_response.get("messages")
                if not isinstance(ai_message_list, list):
                     # Handle cases where the AI might return an empty list or just the outer object
                     if ai_message_list is None and isinstance(ai_response.get("message"), str): # Maybe AI just returned one message?
                         logger.warning("AI returned a single message object instead of a list. Wrapping it.")
                         ai_message_list = [ai_response] # Wrap single object in a list
                     else:
                         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON format ('messages' key not a list or missing)")
            except json.JSONDecodeError as decode_error:
                 logger.error(f"❌ Failed to parse OpenAI response JSON: {decode_error} - Content: {content}")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON content")
            except Exception as parse_exc:
                 logger.error(f"❌ Error processing AI response structure: {parse_exc}")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error processing AI response: {parse_exc}")

            logger.info(f"✅ Successfully parsed {len(ai_message_list)} messages from AI with days_from_today structure.")

            # --- Process and Store Drafts ---
            roadmap_drafts_for_response = []
            business_tz_str = business.timezone or "UTC" # Get business timezone, default to UTC
            business_tz = get_business_timezone(business_tz_str) # Get timezone object

            logger.info(f"ℹ️ Processing {len(ai_message_list)} DRAFT messages from AI response using Business Timezone: {business_tz_str}")

            for idx, msg_data in enumerate(ai_message_list):
                if not isinstance(msg_data, dict) or not all(k in msg_data for k in ["message", "days_from_today", "purpose"]):
                    logger.warning(f"⚠️ Skipping invalid draft message item at index {idx}: {msg_data}")
                    continue

                try:
                    days_from_today = int(msg_data.get("days_from_today"))
                    if days_from_today < 0: # Handle potential negative days from AI
                         logger.warning(f"⚠️ AI returned negative days_from_today ({days_from_today}), using 0 instead.")
                         days_from_today = 0

                    # --- Improved Time Calculation Logic ---
                    target_date_utc = (datetime.utcnow() + timedelta(days=days_from_today)).date()

                    # Define the target time (10:00 AM)
                    target_local_time = time(10, 0, 0)

                    # Combine date and time - creating a NAIVE datetime first
                    naive_local_dt = datetime.combine(target_date_utc, target_local_time)

                    # Localize the naive datetime to the business's timezone
                    localized_dt = business_tz.localize(naive_local_dt)

                    # Convert the localized datetime back to UTC for storage
                    scheduled_time_utc = localized_dt.astimezone(pytz.UTC)

                    logger.debug(f"  Draft {idx+1}: days={days_from_today} -> TargetDateUTC={target_date_utc} -> TargetLocalTime={target_local_time} -> LocalizedDT={localized_dt} -> ScheduledUTC={scheduled_time_utc}")

                except (ValueError, TypeError, KeyError) as e:
                    logger.error(f"❌ Error calculating scheduled time for draft (days_from_today='{msg_data.get('days_from_today')}', index={idx}): {e}. Falling back to simple UTC addition.")
                    # Fallback: simple UTC addition if calculation fails
                    base_time = datetime.utcnow()
                    scheduled_time_utc = base_time + timedelta(days=int(msg_data.get("days_from_today", idx + 1))) # Use original fallback if needed

                message_content = str(msg_data.get("message", ""))[:160] # Enforce length limit

                # Create RoadmapMessage record
                roadmap_draft = RoadmapMessage(
                    customer_id=customer.id,
                    business_id=business.id,
                    smsContent=message_content,
                    # Store the calculated UTC time. The 'smsTiming' text is less critical now.
                    smsTiming=f"{days_from_today} days from today", # Keep for reference if needed
                    send_datetime_utc=scheduled_time_utc,
                    status="draft",
                    relevance=str(msg_data.get("purpose", "Customer engagement")),
                    message_id=None
                )
                self.db.add(roadmap_draft)
                try:
                    self.db.flush() # Flush to get ID before validation if needed
                    self.db.refresh(roadmap_draft) # Refresh to get current state
                except Exception as rm_flush_exc:
                     self.db.rollback()
                     logger.exception(f"❌ DB Error flushing roadmap draft: {rm_flush_exc}")
                     logger.error(f"Failing draft data: {msg_data}")
                     # Don't raise HTTPException here, let the outer handler catch DB errors after loop
                     raise # Re-raise to be caught by the outer try-except

                # Create Pydantic response model (ensure validation occurs)
                try:
                    # Make sure the model validation uses the correct aliases
                    response_draft_model = RoadmapMessageResponse.model_validate(roadmap_draft)
                    roadmap_drafts_for_response.append(response_draft_model)
                except Exception as validation_error:
                     # Log validation errors, but don't necessarily stop the whole process
                     logger.error(f"❌ Failed to validate RoadmapMessageResponse Pydantic model for draft ID {roadmap_draft.id}: {validation_error}")
                     # Continue processing other messages if one fails validation

            # --- Final Commit ---
            self.db.commit()
            logger.info(f"✅ Successfully created {len(roadmap_drafts_for_response)} roadmap DRAFTS in DB for customer {data.customer_id}.")

            # --- Return Success Response ---
            return RoadmapResponse(
                status="success",
                message="Roadmap drafts generated successfully",
                roadmap=roadmap_drafts_for_response,
                total_messages=len(roadmap_drafts_for_response),
                customer_info=customer_context,
                business_info=business_context
            )

        # --- Error Handling ---
        except HTTPException as http_exc:
            # Log and re-raise HTTP exceptions (like 404, 400 from parsing)
            logger.error(f"HTTP Error generating roadmap for customer {data.customer_id}: {http_exc.status_code} - {http_exc.detail}")
            self.db.rollback() # Rollback on HTTP errors too
            raise http_exc
        except openai.OpenAIError as ai_error:
             # Handle specific OpenAI errors
             self.db.rollback()
             logger.error(f"❌ OpenAI API Error generating roadmap for customer {data.customer_id}: {ai_error}")
             raise HTTPException(
                 status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                 detail=f"AI service error: {str(ai_error)}"
             )
        except Exception as e:
            # Catch any other unexpected errors (DB errors, validation errors not caught, etc.)
            self.db.rollback()
            logger.exception(f"❌ Unexpected Error generating roadmap for customer {data.customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An internal server error occurred while generating the roadmap drafts."
            )

    async def generate_sms_response(self, message: str, customer_id: int, business_id: int) -> str:
        """
        Generates a one-off AI reply to an inbound SMS message using business tone and customer context.
        (This method remains unchanged from your original version)
        """
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        # Style
        style_service = StyleService()
        class StyleWrapper:
            def __init__(self, style_dict): self.style_analysis = style_dict or {}
        style = StyleWrapper(await style_service.get_style_guide(business.id, self.db))
        style_guide = style.style_analysis if style and style.style_analysis else {}

        rep_name = business.representative_name or business.business_name # Fallback for signature

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
            model="gpt-4o", # Or your preferred model for replies
            messages=[{"role": "system", "content": "You craft helpful and friendly SMS replies."},
                      {"role": "user", "content": prompt}],
            max_tokens=100 # Limit reply length slightly
        )

        content = response.choices[0].message.content.strip()
        logger.info(f"🧠 One-off AI reply generated for customer {customer_id}: {content}")
        return content

    # --- analyze_customer_response method (keep as is or update similarly if needed) ---
    async def analyze_customer_response(self, customer_id: int, message: str) -> dict:
        """
        Analyzes a customer's response using AI to determine sentiment and next steps
        (Placeholder - Keep your existing implementation or add one later)
        """
        logger.warning("analyze_customer_response not fully implemented yet.")
        # (Existing implementation - review error handling and logging if used)
        # ...
        pass # Placeholder if not implemented yet or keep existing code
        return {"sentiment": "unknown", "next_step": "review_manually"} # Example placeholder response