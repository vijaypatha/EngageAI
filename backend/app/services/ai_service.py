# app/services/ai_service.py
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
# Only import models needed for THIS step
from app.models import Customer, BusinessProfile, RoadmapMessage # Removed Message, Conversation
from app.schemas import RoadmapGenerate, RoadmapResponse, RoadmapMessageResponse
from datetime import datetime, timedelta
import openai
from app.config import settings
import logging
import json
# No uuid needed here anymore

logger = logging.getLogger(__name__)

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
        for a customer using AI.
        """
        try:
            # Get customer and business info (remains the same)
            customer = self.db.query(Customer).filter(Customer.id == data.customer_id).first()
            if not customer:
                 logger.warning(f"Customer not found for ID: {data.customer_id}")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer with ID {data.customer_id} not found")
            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == data.business_id).first()
            if not business:
                 logger.warning(f"Business not found for ID: {data.business_id}")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with ID {data.business_id} not found")

            from app.services.style_service import StyleService

            style_service = StyleService()

# Wrap the dict into an object safely
            class StyleWrapper:
                 def __init__(self, style_dict):
                    self.style_analysis = style_dict or {}

            style = StyleWrapper(await style_service.get_style_guide(business.id, self.db))

# Parse style fields
            style_guide = style.style_analysis if style and style.style_analysis else {}

            # Prepare new smart context for AI
            business_context = {
                "name": business.business_name,
                "industry": business.industry,
                "goal": business.business_goal,
                "services": business.primary_services,
                "representative_name": business.representative_name or ""
            }
            customer_context = {
                "name": customer.customer_name,
                "lifecycle_stage": customer.lifecycle_stage,
                "pain_points": customer.pain_points,
                "relationship_notes": customer.interaction_history
            }

            # Light relationship note parsing for birthday, language
            relationship_notes = (customer.interaction_history or "").lower()
            special_dates = {}
            if "birthday" in relationship_notes:
                special_dates["birthday_mentioned"] = True
            preferred_language = "Spanish" if "spanish" in relationship_notes else "English"

            # Build messages_for_openai block (updated as per new instructions)
            messages_for_openai = [
                {
                    "role": "system",
                    "content": (
                        "You are a caring communication assistant who helps small businesses build lasting, authentic relationships "
                        "with their customers through thoughtful and natural SMS messages.\n\n"
                        "You prioritize warmth, sincerity, and genuine human connection.\n\n"
                        "On birthdays and major holidays, you send heartfelt wishes only — no promotions, no service offers.\n\n"
                        "On regular engagement messages, you may gently remind the customer that the business is available to support them if needed, especially if the business goal is growth.\n\n"
                        "You must match the business owner's tone, style, and key phrases naturally.\n\n"
                        "Always end each SMS with a friendly signature like: '- {representative_name} from {business_name}'.\n\n"
                        "Keep each SMS friendly, personal, and under 160 characters."
                    )
                },
                {
                    "role": "user",
                    "content": f"""
Business Profile:
{json.dumps(business_context, indent=2)}

Customer Profile:
{json.dumps(customer_context, indent=2)}

Business Owner Communication Style:
{json.dumps(style_guide, indent=2)}

Important Dates and Events:
{json.dumps(special_dates, indent=2)}

Language Preference:
{preferred_language}

Preferred Engagement Strategy:
{business.business_goal or "No specific strategy provided."}

---

TASK:

- Generate a personalized roadmap of SMS messages based on the above information.
- If a birthday date is provided:
  - Create one special birthday message scheduled 3–5 days before the birthday.
  - Birthday messages must be warm, caring well-wishes with NO promotions, NO service offers.
- If major holidays are provided:
  - Create one special holiday message scheduled 1–3 days before each holiday.
  - Holiday messages must be pure greetings — no promotions unless explicitly instructed.
- For general engagement:
  - If business goal includes 'growth', you may gently suggest support or services in regular (non-event) messages.
  - Otherwise, focus on relationship nurturing with light check-ins.
- Always end each SMS with the representative's name and business name (e.g., "- Rose from Buds Grooming").
- Write all SMS messages in the customer's preferred language.
- Keep messages natural, friendly, and under 160 characters.
- Output ONLY a valid JSON object with one key: "messages", containing an array of message objects.

Each object must have:
- "message" (string) — the SMS content
- "days_from_today" (integer) — number of days from today to schedule the message
- "purpose" (string) — a short explanation of the goal for this message
"""
                }
            ]
            logger.info(f"ℹ️ Sending request to OpenAI for customer {data.customer_id}, business {data.business_id}")
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages_for_openai,
                response_format={"type": "json_object"}
            )


            # Response parsing (remains the same)
            content = response.choices[0].message.content
            logger.info("🧠 OpenAI raw response: %s", content)
            try:
                ai_response = json.loads(content)
                if not isinstance(ai_response, dict):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON format (not an object)")
                ai_message_list = ai_response.get("messages")
                if not isinstance(ai_message_list, list):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON format ('messages' not a list or missing)")
            except json.JSONDecodeError as decode_error:
                 logger.error(f"❌ Failed to parse OpenAI response JSON: {decode_error} - Content: {content}")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI returned invalid JSON content")
            except Exception as parse_exc:
                 logger.error(f"❌ Error processing AI response structure: {parse_exc}")
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error processing AI response: {parse_exc}")

            logger.info(f"✅ Successfully parsed {len(ai_message_list)} messages from AI with days_from_today structure.")

            roadmap_drafts_for_response = [] # List to hold Pydantic models for the API response

            base_time = datetime.utcnow()
            current_scheduled_time = base_time

            logger.info(f"ℹ️ Processing {len(ai_message_list)} DRAFT messages from AI response.")

            # Loop to create RoadmapMessage drafts (remains the same)
            for idx, msg_data in enumerate(ai_message_list):
                if not isinstance(msg_data, dict) or not all(k in msg_data for k in ["message", "days_from_today", "purpose"]):
                    logger.warning(f"⚠️ Skipping invalid draft message item at index {idx}: {msg_data}")
                    continue

                days_from_today = int(msg_data.get("days_from_today", idx + 1))
                scheduled_time = base_time + timedelta(days=days_from_today)

                message_content = str(msg_data.get("message", ""))[:160]

                # Create ONLY RoadmapMessage record (remains the same)
                roadmap_draft = RoadmapMessage(
                    customer_id=customer.id,
                    business_id=business.id,
                    smsContent=message_content,
                    smsTiming=f"{days_from_today} days from today",
                    send_datetime_utc=scheduled_time,
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
                     raise HTTPException(status_code=500, detail=f"Database error creating roadmap draft: {rm_flush_exc}")

                # Create Pydantic response model (remains the same)
                try:
                    response_draft_model = RoadmapMessageResponse.model_validate(roadmap_draft)
                    roadmap_drafts_for_response.append(response_draft_model)
                except Exception as validation_error:
                     logger.error(f"❌ Failed to validate RoadmapMessageResponse for draft ID {roadmap_draft.id}: {validation_error}")


            # --- Final Commit ---
            self.db.commit()
            logger.info(f"✅ Successfully created {len(roadmap_drafts_for_response)} roadmap DRAFTS in DB for customer {data.customer_id}.")

            # Return the final Pydantic response model
            # --- FIX: Use .get() for safer dictionary access ---
            return RoadmapResponse(
                status="success",
                message="Roadmap drafts generated successfully",
                roadmap=roadmap_drafts_for_response,
                total_messages=len(roadmap_drafts_for_response),
                customer_info=customer_context, # Use .get() with default
                business_info=business_context  # Use .get() with default
            )

        # --- Keep existing except blocks ---
        except HTTPException as http_exc:
            logger.error(f"HTTP Error generating roadmap drafts for customer {data.customer_id}: {http_exc.status_code} - {http_exc.detail}")
            raise http_exc
        except openai.OpenAIError as ai_error:
             self.db.rollback()
             logger.error(f"❌ OpenAI API Error generating drafts for customer {data.customer_id}: {ai_error}")
             raise HTTPException(
                 status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                 detail=f"AI service error: {str(ai_error)}"
             )
        except Exception as e:
            self.db.rollback()
            logger.exception(f"❌ Unexpected Error generating roadmap drafts for customer {data.customer_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An internal server error occurred while generating the roadmap drafts."
            )

    async def generate_sms_response(self, message: str, customer_id: int, business_id: int) -> str:
        """
        Generates a one-off AI reply to an inbound SMS message using business tone and customer context.
        """
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        # Style
        from app.services.style_service import StyleService
        style_service = StyleService()
        class StyleWrapper:
            def __init__(self, style_dict): self.style_analysis = style_dict or {}
        style = StyleWrapper(await style_service.get_style_guide(business.id, self.db))
        style_guide = style.style_analysis if style and style.style_analysis else {}

        prompt = f"""
You are a friendly assistant for {business.business_name}, a {business.industry} business.

The business owner is {business.representative_name} and prefers this tone and style:
{json.dumps(style_guide, indent=2)}

The customer is {customer.customer_name}, who previously shared:
{customer.interaction_history or "No interaction history."}

They just sent this message:
"{message}"

Please draft a friendly, natural-sounding SMS reply that fits the business tone and maintains the relationship. Keep it under 160 characters. Do not include promotions unless relevant.
Always sign off with the business owner's name like: "- {business.representative_name}".
"""

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}],
        )

        content = response.choices[0].message.content.strip()
        logger.info(f"🧠 One-off AI reply generated: {content}")
        return content

    # --- analyze_customer_response method (keep as is or update similarly if needed) ---
    async def analyze_customer_response(self, customer_id: int, message: str) -> dict:
        """
        Analyzes a customer's response using AI to determine sentiment and next steps
        """
        # (Existing implementation - review error handling and logging if used)
        # ...
        pass # Placeholder if not implemented yet or keep existing code