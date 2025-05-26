# backend/app/services/appointment_ai_service.py
import logging
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from sqlalchemy.orm import Session

import openai # Ensure openai is imported
import pytz

from app import models # Import top-level models
from app.models import BusinessProfile, Customer, AppointmentRequest # Specific models
from app import schemas
from app.schemas import (
    AppointmentAIResponse,
    AppointmentTimePreference,
    AppointmentIntent, # Enum from schemas
    AppointmentActionContextPayload # New schema for context
)
from app.timezone_utils import get_business_timezone, get_utc_now

logger = logging.getLogger(__name__)

class AppointmentAIService:
    def __init__(self, db: Optional[Session] = None):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.error("OPENAI_API_KEY not configured for AppointmentAIService.")
            self.client = None
        else:
            # Ensure you are using the correct client initialization for your openai library version
            # For openai >= 1.0.0
            self.client = openai.OpenAI(api_key=self.api_key)
            # For openai < 1.0.0, it would be:
            # openai.api_key = self.api_key
            # self.client = openai # And calls would be openai.ChatCompletion.create()
        self.db = db

    async def parse_appointment_sms(
        self,
        sms_body: str,
        business: models.BusinessProfile,
        customer: Optional[models.Customer] = None,
        is_owner_message: bool = False,
        last_business_message_text: Optional[str] = None # ADDED: Context from last business message
    ) -> schemas.AppointmentAIResponse:
        logger.info(f"AI Service: Parsing SMS. Business ID {business.id}, OwnerMsg: {is_owner_message}, SMS: '{sms_body}', LastBizMsg: '{last_business_message_text if last_business_message_text else 'N/A'}'") # MODIFIED log

        if not self.client:
            logger.error("OpenAI client not available in AppointmentAIService. Returning error response.")
            return schemas.AppointmentAIResponse(
                intent=schemas.AppointmentIntent.ERROR_PARSING, datetime_preferences=[],
                confidence_score=0.0, requires_clarification=True,
                clarification_question="AI service not available.",
                failure_reason="OpenAI client not initialized."
            )

        business_local_tz_obj = get_business_timezone(business.timezone)
        today_in_business_tz_str = datetime.now(business_local_tz_obj).strftime('%A, %B %d, %Y %I:%M %p %Z')

        customer_info = f"from Customer {customer.customer_name or customer.phone if customer else 'Unknown Customer'}"
        message_source_context = f"This SMS is from the business owner, {business.representative_name or business.business_name}, proposing an appointment to {customer_info}." if is_owner_message else f"This SMS is {customer_info}."
        available_intents = ", ".join([f"'{intent.value}'" for intent in schemas.AppointmentIntent if not intent.value.startswith("owner_action_")])

        # ADDED: Enhanced context for last business message
        last_business_message_context_prompt = ""
        if last_business_message_text and not is_owner_message: # Only add this context for customer messages
            last_business_message_context_prompt = f"""
        Crucial Context: The previous SMS message sent by the business to this customer was: "{last_business_message_text}".
        Consider if the customer's current SMS is a direct response to this previous message, especially if it contained a proposed time or an RSVP request.
        For example, if the business said "Confirm for 3pm?" or "Yoga class at 7pm, please RSVP", and the customer says "Yes", "I'll be there", or "Sounds good".
        """

        prompt_content = f"""
        You are an expert assistant for '{business.business_name}' helping manage appointment scheduling via SMS.
        The business's local timezone is {business.timezone}.
        Current date and time for the business: {today_in_business_tz_str}.
        {message_source_context}
        {last_business_message_context_prompt}

        Analyze the following SMS message (from {"owner" if is_owner_message else "customer"}):
        SMS: "{sms_body}"

        Your tasks are:
        1. Determine the primary 'intent' of this message regarding appointments. Choose from: {available_intents}.
           - If 'is_owner_message' is true and the owner is suggesting a time, use '{schemas.AppointmentIntent.OWNER_PROPOSAL.value}'.
           - For customer messages: Use '{schemas.AppointmentIntent.REQUEST_APPOINTMENT.value}', '{schemas.AppointmentIntent.CONFIRMATION.value}', '{schemas.AppointmentIntent.CANCELLATION.value}', '{schemas.AppointmentIntent.RESCHEDULE.value}', '{schemas.AppointmentIntent.QUERY_AVAILABILITY.value}', '{schemas.AppointmentIntent.AMBIGUOUS_APPOINTMENT_RELATED.value}', '{schemas.AppointmentIntent.NEEDS_CLARIFICATION.value}', or '{schemas.AppointmentIntent.NOT_APPOINTMENT.value}'.
           - **IMPORTANT Human-like Behavior**: If the customer's SMS (e.g., "I'll be there", "Yes", "Sounds good", "Okay", "Confirm", "RSVP yes") is a clear, affirmative response to a specific time, date, or named event (like "yoga class today at 7PM") mentioned in the 'Crucial Context' (the last business message), the 'intent' MUST be '{schemas.AppointmentIntent.CONFIRMATION.value}'.
        2. Extract 'datetime_preferences': A list of potential date/time slots. Each item: {{ 'datetime_str', 'resolved_utc_start_time', 'resolved_utc_end_time' }}. Resolve to future business local time then convert to ISO 8601 UTC. For dayparts (morning=9AM, afternoon=1PM, evening=6PM local), or just day (assume 10AM local). If unresolvable or just text, null for resolved times.
           - **If the intent is '{schemas.AppointmentIntent.CONFIRMATION.value}' AND directly relates to a specific time/event from the 'Crucial Context' (e.g., customer says "I'll be there" after business says "Yoga class at 7pm, please RSVP"), then 'datetime_preferences' MUST contain one item where 'datetime_str' is the confirmed time/event description (e.g., "7pm today for Yoga") and 'resolved_utc_start_time' is that specific time, accurately parsed from the 'Crucial Context' and 'Current date and time for the business', then converted to UTC.** Assume the business message implies 'today' if no other date is specified for same-day events like "today at 7PM".
        3. 'confidence_score' (float, 0.0-1.0).
        4. 'requires_clarification' (boolean). **If intent is '{schemas.AppointmentIntent.CONFIRMATION.value}' based on a clear affirmative response to a specific time in 'Crucial Context', this MUST be 'false'.**
        5. If 'requires_clarification' is true, provide a 'clarification_question' (string). **If intent is '{schemas.AppointmentIntent.CONFIRMATION.value}' of a clear time from 'Crucial Context', this MUST be 'null'.**
        6. 'parsed_intent_details' (string | null) for brief explanation if complex (e.g., "Customer confirmed the 7 PM yoga class mentioned in the business's last message.").

        Output ONLY a valid JSON object.
        {{
          "intent": string,
          "datetime_preferences": [{{ "datetime_str": string | null, "resolved_utc_start_time": string (ISO 8601 UTC) | null, "resolved_utc_end_time": string (ISO 8601 UTC) | null }}] | null,
          "confidence_score": float,
          "requires_clarification": boolean,
          "clarification_question": string | null,
          "parsed_intent_details": string | null
        }}
        """
        default_ai_response = schemas.AppointmentAIResponse(
            intent=schemas.AppointmentIntent.ERROR_PARSING, datetime_preferences=[],
            confidence_score=0.0, requires_clarification=True,
            clarification_question="Could not understand the request.",
            parsed_intent_details="AI service failed to process the message.",
            failure_reason="Default response due to error."
        )
        try:
            completion = self.client.chat.completions.create(
                model=os.getenv("OPENAI_APPOINTMENT_MODEL_NAME", "gpt-4o"),
                messages=[
                    {"role": "system", "content": "You are an intelligent assistant analyzing SMS for appointment scheduling. Respond strictly in the specified JSON format, paying close attention to contextual cues from previous messages."},
                    {"role": "user", "content": prompt_content}
                ],
                response_format={"type": "json_object"}, temperature=0.0, max_tokens=600 # MODIFIED: temperature to 0.0 for more deterministic output given strong instructions, increased max_tokens slightly
            )
            raw_response_content = completion.choices[0].message.content
            logger.debug(f"AI raw JSON response for SMS parsing: {raw_response_content}")
            if not raw_response_content:
                default_ai_response.failure_reason = "AI returned an empty response."
                return default_ai_response
            
            ai_json = json.loads(raw_response_content)
            
            intent_str = ai_json.get("intent", schemas.AppointmentIntent.ERROR_PARSING.value)
            try:
                parsed_intent = schemas.AppointmentIntent(intent_str)
            except ValueError:
                logger.warning(f"AI returned an unknown intent string '{intent_str}'. Defaulting to ERROR_PARSING.")
                parsed_intent = schemas.AppointmentIntent.ERROR_PARSING
            
            parsed_datetime_preferences = []
            ai_dt_prefs = ai_json.get("datetime_preferences")
            if isinstance(ai_dt_prefs, list):
                for pref_dict in ai_dt_prefs:
                    if not isinstance(pref_dict, dict): continue
                    start_time_utc, end_time_utc = None, None
                    try:
                        if st_str := pref_dict.get("resolved_utc_start_time"):
                            start_time_utc = datetime.fromisoformat(st_str.replace('Z', '+00:00'))
                        if et_str := pref_dict.get("resolved_utc_end_time"):
                            end_time_utc = datetime.fromisoformat(et_str.replace('Z', '+00:00'))
                        parsed_datetime_preferences.append(schemas.AppointmentTimePreference(
                            datetime_str=pref_dict.get("datetime_str"), start_time=start_time_utc, end_time=end_time_utc
                        ))
                    except ValueError as ve:
                        logger.warning(f"Error parsing datetime string from AI: {pref_dict}. Error: {ve}")
                        if pref_dict.get("datetime_str"):
                             parsed_datetime_preferences.append(schemas.AppointmentTimePreference(
                                datetime_str=pref_dict.get("datetime_str"), start_time=None, end_time=None))
            
            # Ensure requires_clarification is consistent with prompt instructions for CONFIRMATION
            requires_clarification_val = bool(ai_json.get("requires_clarification", True)) # Default to True if not provided
            clarification_question_val = ai_json.get("clarification_question")

            if parsed_intent == schemas.AppointmentIntent.CONFIRMATION and \
               len(parsed_datetime_preferences) > 0 and parsed_datetime_preferences[0].start_time is not None:
                # If AI correctly identified a CONFIRMATION of a specific time from context,
                # override requires_clarification and clarification_question based on prompt rules.
                is_contextual_confirmation = last_business_message_text is not None # Heuristic: if context was provided, AI might have used it
                if is_contextual_confirmation: # More specific check could be if parsed_intent_details mentions context
                    logger.info(f"AI parsed contextual confirmation for intent {parsed_intent.value}. Setting requires_clarification=False.")
                    requires_clarification_val = False
                    clarification_question_val = None
            elif not parsed_datetime_preferences and parsed_intent not in [
                schemas.AppointmentIntent.CONFIRMATION, schemas.AppointmentIntent.CANCELLATION,
                schemas.AppointmentIntent.NOT_APPOINTMENT, schemas.AppointmentIntent.OWNER_PROPOSAL
            ]: # MODIFIED: Added OWNER_PROPOSAL to not default requires_clarification to True if no datetime prefs.
                 requires_clarification_val = True


            final_response = schemas.AppointmentAIResponse(
                intent=parsed_intent, datetime_preferences=parsed_datetime_preferences,
                confidence_score=float(ai_json.get("confidence_score", 0.0)),
                requires_clarification=requires_clarification_val,
                clarification_question=clarification_question_val,
                parsed_intent_details=ai_json.get("parsed_intent_details"), failure_reason=None
            )
            logger.info(f"AI Parsed SMS. Intent: {parsed_intent.value if hasattr(parsed_intent, 'value') else str(parsed_intent)}, Prefs: {len(final_response.datetime_preferences)}, Clarify: {final_response.requires_clarification}, Detail: {final_response.parsed_intent_details}") # MODIFIED log
            return final_response
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from AI response: {raw_response_content if 'raw_response_content' in locals() else 'N/A'}. Error: {e}", exc_info=True)
            default_ai_response.failure_reason = f"JSONDecodeError: {e}"
            return default_ai_response
        except openai.APIError as e: 
            logger.error(f"OpenAI API error during SMS parsing: {e}", exc_info=True)
            default_ai_response.failure_reason = f"OpenAI APIError: {type(e).__name__} - {e}"
            return default_ai_response
        except Exception as e:
            logger.error(f"Unexpected error in parse_appointment_sms: {e}", exc_info=True)
            default_ai_response.failure_reason = f"Unexpected error in AI service: {type(e).__name__} - {e}"
            return default_ai_response

    async def draft_appointment_related_sms(
        self,
        business: models.BusinessProfile,
        customer_name: Optional[str],
        intent_type: Union[schemas.AppointmentIntent, str],
        time_details: Optional[str] = None, # e.g., "7 PM today", "tomorrow afternoon"
        original_customer_request: Optional[str] = None,
        owner_reason_for_action: Optional[str] = None,
        clarification_question_from_ai: Optional[str] = None,
        alternative_slots_text: Optional[List[str]] = None,
        owner_proposed_new_time_text: Optional[str] = None
    ) -> str:
        if not self.client:
            logger.error("OpenAI client not available for drafting SMS.")
            return f"We'll be in touch about {time_details or 'your request'} shortly. - {business.representative_name or business.business_name}"

        intent_val = intent_type.value if isinstance(intent_type, schemas.AppointmentIntent) else intent_type
        logger.info(f"AI Service: Drafting SMS for intent '{intent_val}' for Business ID: {business.id}, TimeDetails: '{time_details}'") # MODIFIED log

        style_guide_context = "The business owner prefers a friendly and professional tone. Be human-like and empathetic." # MODIFIED
        representative_name = business.representative_name or business.business_name
        cust_name_part = f"{customer_name}, " if customer_name else ""
        instruction = "" 

        if intent_val == schemas.AppointmentIntent.CONFIRMATION.value:
            # MODIFIED: Enhanced prompt for more human-like confirmation
            time_clause = f"for the appointment around {time_details}" if time_details else "for the appointment"
            instruction = f"Write a warm and friendly SMS to {cust_name_part}acknowledging their confirmation {time_clause}. Express enthusiasm (e.g., 'we're excited to see you!', 'Thanks for the RSVP!', 'That's great to hear!'). If a specific time was part of '{time_details}', subtly acknowledge it as confirmed (e.g., 'See you then!', 'Looking forward to it at {time_details}'). Keep it brief, positive, and ensure it sounds like a human wrote it."
        elif intent_val == schemas.AppointmentIntent.NEEDS_CLARIFICATION.value or intent_val == "request_clarification_on_time":
            question = clarification_question_from_ai or 'Could you please provide some specific days or times that work for you?'
            # MODIFIED: Make clarification more gentle if it follows a vague positive response.
            if original_customer_request and any(kw in original_customer_request.lower() for kw in ["i'll be there", "yes", "ok"]):
                 instruction = f"Write a friendly SMS to {cust_name_part}thanking them for their response ('{original_customer_request}'). Then, gently ask for more specific timing details: {question}"
            else:
                instruction = f"Write a friendly SMS to {cust_name_part}acknowledging their appointment request ('{original_customer_request or 'your message'}'). Ask: {question}"
        elif intent_val == schemas.AppointmentIntent.OWNER_ACTION_CONFIRM.value:
            instruction = f"Write a friendly SMS to {cust_name_part}confirming their appointment for {time_details}."
        elif intent_val == schemas.AppointmentIntent.OWNER_ACTION_SUGGEST_RESCHEDULE.value:
            alt_slots_str = (", or ".join(alternative_slots_text) if alternative_slots_text else "another time that might work for you")
            base_suggestion = owner_proposed_new_time_text or time_details
            instruction = (f"Write a friendly SMS to {cust_name_part}regarding their appointment request "
                           f"for '{original_customer_request or 'the previously discussed time'}'. "
                           f"Explain that time is unavailable (Reason: {owner_reason_for_action or 'scheduling conflict'}). "
                           f"Propose {base_suggestion}. Ask if that works or if they prefer {alt_slots_str}.")
        elif intent_val == schemas.AppointmentIntent.OWNER_ACTION_DECLINE.value:
            instruction = (f"Write a polite SMS to {cust_name_part}informing them that unfortunately their appointment request "
                           f"for {time_details or original_customer_request or 'the requested time'} cannot be accommodated at this moment "
                           f"(Reason: {owner_reason_for_action or 'we are fully booked'}). Apologize for any inconvenience and suggest they call if they wish to discuss other options.")
        elif intent_val == "cancel_appointment_owner" or (intent_val == schemas.AppointmentIntent.CANCELLATION.value and owner_reason_for_action):
            reason_text = f" due to: {owner_reason_for_action}" if owner_reason_for_action else ""
            instruction = f"Write a polite SMS to {cust_name_part}informing them that unfortunately their confirmed appointment for {time_details} needs to be cancelled{reason_text}. Apologize for any inconvenience."
        else:
            logger.warning(f"Specific drafting logic not fully detailed for intent_type: {intent_val}. Creating a general acknowledgement.")
            instruction = f"Write a friendly SMS to {cust_name_part}acknowledging their message ('{original_customer_request or time_details or 'your recent message'}'). State that you will review it and get back to them."


        prompt_content = f"""
        You are {representative_name} from {business.business_name}.
        Your communication style is: {style_guide_context}
        Customer's Name (if known): {customer_name or 'Valued Customer'}
        Task: {instruction}
        The SMS must be concise, ideally under 160 characters, and sound natural and human-like.
        End with your signature: "- {representative_name}".
        SMS Draft:
        """
        try:
            completion = self.client.chat.completions.create(
                model=os.getenv("OPENAI_APPOINTMENT_DRAFT_MODEL_NAME", "gpt-4o"),
                messages=[
                    {"role": "system", "content": f"You are an SMS drafting assistant for {representative_name} of {business.business_name}. Adhere to the provided style and instructions. Be concise, friendly, and human-like."},
                    {"role": "user", "content": prompt_content}
                ],
                temperature=0.7, max_tokens=120 
            )
            draft = completion.choices[0].message.content.strip()
            # Ensure signature is present, but avoid double signing if AI already included it.
            sig = f"- {representative_name}"
            if not draft.endswith(sig): # Check if it ends with the signature
                # Remove any partial or alternative AI signature before adding the correct one
                if draft.rfind("- ") > draft.length * 0.7 : # Heuristic: if a dash and space are near the end
                    draft = draft[:draft.rfind("- ")].strip()
                draft += f" {sig}" # Add with a space if not already ending with it.
            
            # Normalize signature if AI added it slightly differently.
            if sig in draft and not draft.endswith(sig):
                parts = draft.split(sig)
                if len(parts) > 1 and parts[-1].strip() == "": # If signature is there but with trailing spaces
                    draft = parts[0].strip() + f" {sig}"

            logger.info(f"AI drafted SMS for '{intent_val}': {draft}")
            return draft
        except Exception as e:
            logger.error(f"Error drafting appointment SMS with AI: {e}", exc_info=True)
            fallback_time = time_details or "your recent request"
            return f"We'll be in touch about {fallback_time} soon. - {representative_name}"
    
    async def parse_owner_availability_exception_note(
        self,
        exception_note: str,
        business: models.BusinessProfile,
        base_hours_description: str
    ) -> Dict[str, Any]:
        logger.info(f"AI Service: Parsing owner availability exception note for Business ID {business.id}. Note: '{exception_note}'")
        if not self.client: 
            return {"exceptions": [], "parsing_confidence": 0.0, "requires_owner_clarification": True, "clarification_notes": "AI service not available."}
        if not exception_note or not exception_note.strip(): 
             return {"exceptions": [], "parsing_confidence": 1.0, "requires_owner_clarification": False, "clarification_notes": None}

        business_local_tz_str = business.timezone or "UTC"
        business_pytz_tz = get_business_timezone(business_local_tz_str)
        today_in_business_tz_str = get_utc_now().astimezone(business_pytz_tz).strftime('%A, %B %d, %Y')

        prompt_content = f"""
        You are an expert assistant helping a business owner define exceptions to their general availability.
        The business's general availability is described as: "{base_hours_description}".
        The business's local timezone is {business_local_tz_str}.
        For context, today's date in the business's timezone is: {today_in_business_tz_str}. "Daily" typically refers to the days covered by the general availability.

        The owner provided the following text note describing exceptions to their general availability:
        "{exception_note}"

        Your tasks are:
        1. Parse this note into a list of structured 'exceptions'. Each exception object MUST contain:
           - "days_of_week": A list of applicable full weekday names (e.g., ["Wednesday"], ["Monday", "Tuesday", "Friday"]). Determine these based on the note and the general availability context (e.g., "daily" means all days in "{base_hours_description}").
           - "start_time_local": The local start time of the exclusion in HH:MM 24-hour format (e.g., "12:00"), or null if it's an all-day exclusion or not applicable.
           - "end_time_local": The local end time of the exclusion in HH:MM 24-hour format (e.g., "13:00"), or null if it's an all-day exclusion or not applicable.
           - "is_all_day_exclusion": A boolean (true/false), true if the entire day(s) are meant to be excluded.
           - "reason": An optional brief string describing the reason if discernible (e.g., "Lunch", "Closed", "Personal Time").
        2. Provide a "parsing_confidence" score (float, 0.0 to 1.0, where 1.0 is highest confidence).
        3. Indicate if "requires_owner_clarification" (boolean, true if the note is ambiguous or parsing is uncertain).
        4. If clarification is needed, provide brief "clarification_notes" (string, explaining what is unclear).

        Examples of input notes and expected "exceptions" list structure:
        - Input: "closed Wednesdays" -> Expected exception: [{{"days_of_week": ["Wednesday"], "is_all_day_exclusion": True, "start_time_local": null, "end_time_local": null, "reason":"Closed"}}]
        - Input: "lunch daily 12-1pm" (assuming base hours are Mon-Fri) -> Expected exception: [{{"days_of_week": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "start_time_local": "12:00", "end_time_local": "13:00", "is_all_day_exclusion": False, "reason":"Lunch"}}]
        - Input: "no appointments after 3pm on Fridays" -> Expected exception: [{{"days_of_week": ["Friday"], "start_time_local": "15:00", "end_time_local": "23:59", "is_all_day_exclusion": False, "reason":"No appointments after 3pm"}}] (assuming end of day if only start is mentioned for 'after')
        - Input: "take off first Monday of the month" -> This is too complex for simple recurring rules; flag for clarification.

        Output ONLY a valid JSON object with the exact top-level keys: "exceptions", "parsing_confidence", "requires_owner_clarification", "clarification_notes".
        If the note is empty, clearly not availability related, or unparseable into these rules, return an empty "exceptions" list with appropriate confidence and clarification flags.
        """
        default_response = {
            "exceptions": [], "parsing_confidence": 0.0,
            "requires_owner_clarification": True,
            "clarification_notes": "Could not parse the exception note with the AI model."
        }
        raw_response_content = ""
        try:
            logger.debug(f"Sending prompt to OpenAI for exception note parsing (Biz ID: {business.id}): {prompt_content[:500]}...")
            completion = self.client.chat.completions.create(
                model=os.getenv("OPENAI_GENERAL_MODEL_NAME", "gpt-4o"),
                messages=[
                    {"role": "system", "content": "You analyze text notes for business availability exceptions and return structured JSON as per detailed instructions."},
                    {"role": "user", "content": prompt_content}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            raw_response_content = completion.choices[0].message.content
            logger.debug(f"AI raw JSON response for exception note parsing: {raw_response_content}")

            if not raw_response_content: return default_response
            ai_json = json.loads(raw_response_content)
            
            required_keys = ["exceptions", "parsing_confidence", "requires_owner_clarification"]
            if not all(k in ai_json for k in required_keys):
                logger.warning(f"AI response for exception note parsing missing one or more required keys. Response: {ai_json}")
                return default_response
            
            if not isinstance(ai_json.get("exceptions"), list):
                logger.warning(f"AI response 'exceptions' field is not a list. Response: {ai_json}")
                ai_json["exceptions"] = [] 
                ai_json["parsing_confidence"] = 0.1
                ai_json["requires_owner_clarification"] = True
                ai_json["clarification_notes"] = (ai_json.get("clarification_notes") or "") + " AI 'exceptions' was not a list."

            logger.info(f"AI successfully parsed availability exceptions: {len(ai_json.get('exceptions', []))} rules found for Business ID {business.id}.")
            return ai_json

        except json.JSONDecodeError as e: 
            logger.error(f"Failed to decode JSON from AI for exception note. Content: '{raw_response_content}'. Error: {e}", exc_info=True)
            default_response["clarification_notes"] = "AI returned malformed JSON for exception note."
            return default_response
        except openai.APIError as e: 
            logger.error(f"OpenAI API error during exception note parsing for Business ID {business.id}: {e}", exc_info=True)
            default_response["clarification_notes"] = f"OpenAI API Error: {type(e).__name__}"
            return default_response
        except Exception as e: 
            logger.error(f"Unexpected error parsing availability exception note for Business ID {business.id}: {e}", exc_info=True)
            default_response["clarification_notes"] = f"Unexpected error: {type(e).__name__}"
            return default_response
     
    async def parse_owner_manual_time_suggestion(
        self,
        owner_text_suggestion: str,
        business: models.BusinessProfile,
        customer_original_request_text: Optional[str] = None,
        reference_datetime_utc: Optional[datetime] = None
    ) -> Optional[datetime]:
        logger.info(f"AI Service: Parsing owner's manual time suggestion for Business ID {business.id}. Suggestion: '{owner_text_suggestion}'")
        if not self.client: 
            return None
        if not owner_text_suggestion or not owner_text_suggestion.strip(): 
            return None

        business_local_tz_obj = get_business_timezone(business.timezone)
        if reference_datetime_utc:
            current_ref_dt_in_business_tz = reference_datetime_utc.astimezone(business_local_tz_obj)
        else:
            current_ref_dt_in_business_tz = get_utc_now().astimezone(business_local_tz_obj)
        current_ref_dt_str = current_ref_dt_in_business_tz.strftime('%A, %B %d, %Y, %I:%M %p %Z')
        customer_context_str = f"This is in response to a customer's original request for around '{customer_original_request_text}'." if customer_original_request_text else "This is a new time suggestion."

        prompt_content = f"""
        You are an expert assistant helping a business owner specify an appointment time.
        The business owner is in timezone: {business.timezone}.
        The current reference date and time for resolving relative terms (like "tomorrow", "next week", "afternoon") is: {current_ref_dt_str}.
        {customer_context_str}

        The business owner suggested the following time for an appointment:
        "{owner_text_suggestion}"

        Your task is to:
        1. Parse this suggestion into a single, specific, future date and time.
        2. Assume standard business day parts if only a day part is mentioned (e.g., "morning" = 9:00 AM, "afternoon" = 2:00 PM, "evening" = 6:00 PM in the business's local time).
        3. If only a day is mentioned (e.g., "next Friday"), assume a common business hour like 10:00 AM local time.
        4. If the suggestion is too vague or unparseable into a specific future datetime, return null.
        5. The resolved datetime MUST be in the future relative to the current reference time.

        Output ONLY a valid JSON object with a single key "resolved_utc_datetime_iso".
        The value should be the resolved specific future date and time in ISO 8601 UTC format (e.g., "YYYY-MM-DDTHH:MM:SSZ"), or null if unparseable or not in the future.

        Examples (Current Reference: Monday, May 19, 2025, 10:00 AM EDT):
        - Owner Suggestion: "Tomorrow at 2pm" -> Expected JSON: {{"resolved_utc_datetime_iso": "2025-05-20T18:00:00Z"}} (assuming 2 PM EDT is 6 PM UTC)
        - Owner Suggestion: "Next Friday morning" -> Expected JSON: {{"resolved_utc_datetime_iso": "2025-05-30T13:00:00Z"}} (assuming Friday May 30th, 9 AM EDT is 1 PM UTC)
        - Owner Suggestion: "Sometime next week" -> Expected JSON: {{"resolved_utc_datetime_iso": null}} (too vague)
        - Owner Suggestion: "Yesterday" -> Expected JSON: {{"resolved_utc_datetime_iso": null}} (not in future)
        """
        raw_response_content = ""
        try:
            logger.debug(f"Sending prompt to OpenAI for owner time suggestion parsing (Biz ID: {business.id}): {prompt_content[:500]}...")
            completion = self.client.chat.completions.create(
                model=os.getenv("OPENAI_APPOINTMENT_MODEL_NAME", "gpt-4o"),
                messages=[
                    {"role": "system", "content": "You parse free-form text into a specific future UTC datetime in JSON format."},
                    {"role": "user", "content": prompt_content}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            raw_response_content = completion.choices[0].message.content
            logger.debug(f"AI raw JSON response for owner time suggestion: {raw_response_content}")

            if not raw_response_content: return None
            ai_json = json.loads(raw_response_content)
            resolved_utc_iso_str = ai_json.get("resolved_utc_datetime_iso")

            if resolved_utc_iso_str:
                parsed_dt_utc = datetime.fromisoformat(resolved_utc_iso_str.replace('Z', '+00:00'))
                if parsed_dt_utc.tzinfo is None or parsed_dt_utc.tzinfo.utcoffset(parsed_dt_utc) is None:
                    parsed_dt_utc = pytz.utc.localize(parsed_dt_utc)
                else:
                    parsed_dt_utc = parsed_dt_utc.astimezone(pytz.utc)
                
                comparison_dt_utc = reference_datetime_utc if reference_datetime_utc else get_utc_now()
                if parsed_dt_utc > comparison_dt_utc:
                    logger.info(f"AI successfully parsed owner time suggestion to UTC: {parsed_dt_utc.isoformat()} for Business ID {business.id}")
                    return parsed_dt_utc
                else:
                    logger.warning(f"AI parsed owner time suggestion ({parsed_dt_utc.isoformat()}), but it's not in the future compared to {comparison_dt_utc.isoformat()}. Suggestion: '{owner_text_suggestion}'")
                    return None
            else:
                logger.info(f"AI could not parse owner time suggestion: '{owner_text_suggestion}' for Business ID {business.id} into a specific future datetime.")
                return None

        except json.JSONDecodeError as e: 
            logger.error(f"Failed to decode JSON from AI for owner time suggestion. Content: '{raw_response_content}'. Error: {e}", exc_info=True)
            return None
        except openai.APIError as e: 
            logger.error(f"OpenAI API error during owner time suggestion parsing for Business ID {business.id}: {e}", exc_info=True)
            return None
        except ValueError as e: 
            logger.error(f"ValueError parsing datetime string from AI for owner time suggestion. ISO String: '{resolved_utc_iso_str if 'resolved_utc_iso_str' in locals() else 'N/A'}'. Error: {e}", exc_info=True)
            return None
        except Exception as e: 
            logger.error(f"Unexpected error parsing owner time suggestion for Business ID {business.id}: {e}", exc_info=True)
            return None