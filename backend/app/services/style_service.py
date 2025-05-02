# Manages the unique communication style of each business, helping maintain consistent messaging tone and personality
# Business owners can train the system with their preferred way of communicating with customers
from datetime import datetime
import json
import logging
import re
from typing import Dict, Optional, List, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessOwnerStyle, BusinessProfile
from app.schemas import SMSStyleInput, BusinessScenarioCreate
import openai
import os
import traceback

# Configure logging
logger = logging.getLogger(__name__)

def robust_json_extract(content: str) -> Any: # Return type can be Dict or List
    """
    Attempts to robustly extract a JSON object or array from a string,
    handling common LLM formatting issues like markdown code blocks or extra text.
    Does NOT validate the content of the JSON, only the format.
    """
    logger.info("Attempting robust JSON extract...")
    original_content = content # Keep original content for debugging

    try:
        processing_content = content

        # Remove markdown/code formatting like ```json ... ```
        if "```" in processing_content:
            parts = processing_content.split("```")
            # Take the content between the first two ```, assume it's the JSON block
            if len(parts) >= 2:
                processing_content = parts[1]
                # Remove potential 'json' label at the start
                if processing_content.strip().lower().startswith("json"):
                    processing_content = processing_content.strip()[4:].strip()

        # Attempt to find and parse the full JSON object using regex {.*}
        # Or a JSON array using regex [.*]
        # Added flags=re.DOTALL to allow . to match newlines
        json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', processing_content, flags=re.DOTALL)

        if not json_match:
            logger.warning("No JSON object or array pattern found in content.")
            raise ValueError("No JSON object or array pattern found in content")

        raw_json_string = json_match.group(0)
        logger.debug(f"Extracted raw JSON string (first 500 chars): {raw_json_string[:500]}...")

        # Attempt standard JSON load first
        try:
            parsed_json = json.loads(raw_json_string)
            logger.info("Successfully parsed JSON directly.")
            return parsed_json

        except json.JSONDecodeError as e:
            logger.warning(f"Strict JSON load failed: {e}. Attempting common fixes and retry.")
            logger.debug(f"Failed string causing error (first 500 chars): {raw_json_string[:500]}")

            # Apply common OpenAI JSON errors fixes *before* retrying parse
            cleaned_json_string = raw_json_string
            # Remove trailing commas before closing brackets/braces
            cleaned_json_string = re.sub(r',\s*([}\]])', r'\1', cleaned_json_string)
             # Remove comments // or /* */ - LLMs sometimes add these
            cleaned_json_string = re.sub(r'//.*?\n', '', cleaned_json_string) # single line comments
            cleaned_json_string = re.sub(r'/\*.*?\*/', '', cleaned_json_string, flags=re.DOTALL) # multi-line comments
            # Handle cases where the JSON might be wrapped in unexpected characters (less common with response_format="json_object")
            cleaned_json_string = cleaned_json_string.strip()


            try:
                parsed_json_cleaned = json.loads(cleaned_json_string)
                logger.info("Successfully parsed JSON after applying common fixes.")
                return parsed_json_cleaned

            except json.JSONDecodeError as cleaned_e:
                 logger.error(f"JSON load failed even after applying common fixes: {cleaned_e}")
                 logger.error(f"Cleaned string that failed (first 500 chars): {cleaned_json_string[:500]}")
                 # If cleaned JSON still fails, raise the error
                 raise ValueError(f"Failed to parse JSON even after cleaning: {cleaned_e}") from cleaned_e


    except Exception as e:
        # Catch any other unexpected errors during the process
        logger.error(f"An unexpected error occurred during robust_json_extract: {str(e)}")
        logger.debug(f"Original content (first 500 chars): {original_content[:500]}") # Log original content if an unexpected error occurs
        # Re-raise as ValueError as this function is expected to return parsed data or raise
        raise ValueError(f"Failed to extract valid JSON: {e}") from e


async def generate_business_scenarios(business: BusinessProfile, db: Session) -> List[Dict]:
    """
    Generate relevant training scenarios based on business context.

    Args:
        business: BusinessProfile instance
        db: Database session

    Returns:
        List of dictionaries containing generated scenarios, including temporary IDs.

    Raises:
        ValueError: If business profile is incomplete.
        HTTPException: If scenario generation or storage fails due to AI/DB issues.
    """
    if not business:
        raise ValueError("Business profile is required")

    # Check for required business details for scenario generation
    if not all([business.industry, business.business_name, business.business_goal, business.primary_services]):
        missing_info = [
            field for field in ['industry', 'business_name', 'business_goal', 'primary_services']
            if not getattr(business, field)
        ]
        error_msg = f"Business profile incomplete. Missing information: {', '.join(missing_info)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = f"""
    Create 3 SMS training scenarios for a {business.industry} business.
    Business Details:
    - Name: {business.business_name}
    - Goals: {business.business_goal}
    - Services: {business.primary_services}

    For each scenario:
    1. Create a realistic situation this business might face in an SMS communication context.
    2. Classify the context_type using a relevant category (e.g., inquiry, follow_up, appreciation, sales, support, notification, appointment_reminder, confirmation, feedback_request, etc.). Choose the most appropriate category for the scenario.

    IMPORTANT: Return your response in this exact JSON format. It must be a single JSON object with a key "scenarios" containing a list of scenario objects. Ensure the JSON is perfectly formatted, containing only the JSON object without surrounding text or markdown.
    {{
        "scenarios": [
            {{
                "scenario": "specific situation description relevant to SMS",
                "context_type": "chosen_category"
            }},
            // repeat for all 3 scenarios
        ]
    }}

    Requirements for scenarios:
    - Be concise and suitable for SMS length.
    - Highly specific to the business's industry and services.
    - Cover different stages of customer interaction (pre-sale, post-sale, support, etc.).
    - Include business-specific terminology where natural.
    - Align with their stated business goals.
    """

    try:
        logger.info(f"🚀 Generating scenarios for business {business.id}")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert in business communication and customer engagement. Generate realistic SMS scenarios. Always return responses in valid JSON format, containing ONLY the JSON object. DO NOT include markdown code blocks (like ```json) or any other surrounding text."},
                {"role": "user", "content": prompt} # Corrected key here
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )

        response_content = response.choices[0].message.content
        logger.info(f"Raw OpenAI scenario generation response content: {response_content}")

        try:
            # Use the robust extractor - it now just parses JSON, doesn't validate content
            scenarios_data = robust_json_extract(response_content)

            # *** Content Validation for Scenarios Output ***
            if not isinstance(scenarios_data, dict) or "scenarios" not in scenarios_data or not isinstance(scenarios_data.get("scenarios"), list):
                 logger.error(f"AI response structure invalid: expected a dict with 'scenarios' list. Raw content: {response_content}")
                 raise ValueError("Invalid response format from AI service: Expected a JSON object with a 'scenarios' list.")

            generated_scenarios_list = scenarios_data["scenarios"]

            # Allow generating 0 scenarios if the AI decides, although the prompt asks for 3.
            # If len(generated_scenarios_list) == 0:
            #      logger.warning("AI generated an empty list of scenarios.")
            #      # Decide if empty list is an error or acceptable. Raising error for now as 3 were requested.
            #      raise ValueError("AI generated an empty list of scenarios")


            # Validate each item in the list
            stored_scenarios = []
            for item in generated_scenarios_list:
                if not isinstance(item, dict):
                    logger.error(f"Invalid item in scenarios list: not a dictionary. Item: {item}")
                    raise ValueError("Invalid item format in scenarios list")
                if not item.get("scenario") or not item.get("context_type"):
                    logger.error(f"Invalid scenario item: missing 'scenario' or 'context_type'. Item: {item}")
                    raise ValueError("Invalid scenario item: missing required fields")

                # Store scenarios in database
                db_scenario = BusinessOwnerStyle(
                    business_id=business.id,
                    scenario=item["scenario"],
                    context_type=item["context_type"],
                    response="",  # Will be filled by business owner
                    last_analyzed=None # Set this when a response is provided/analyzed
                )
                db.add(db_scenario)
                stored_scenarios.append(db_scenario)

            # Only commit if we successfully generated and validated at least one scenario
            if stored_scenarios:
                try:
                    db.commit()
                    logger.info(f"Successfully stored {len(stored_scenarios)} generated scenarios.")
                except Exception as e:
                    logger.error(f"Database error while storing scenarios: {str(e)}")
                    db.rollback()
                    # Re-raise as HTTPException as this is a critical failure after AI generation
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to store generated scenarios"
                    )
            else:
                 logger.warning("No valid scenarios were generated or found after processing.")
                 # Return an empty list if no valid scenarios could be processed,
                 # but avoid storing anything if validation failed for all.
                 return []


            # Return scenarios for frontend with their new database IDs
            return [{
                "id": s.id,
                "scenario": s.scenario,
                "context_type": s.context_type,
                "example_response": s.response # Include empty response field for consistency
            } for s in stored_scenarios]

        except ValueError as e:
            # Catch ValueErrors raised by robust_json_extract or content validation
            logger.error(f"Data processing error after OpenAI response: {str(e)}")
            # Re-raise as HTTPException as this indicates a problem with the AI output processing
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process AI response: {e}"
            )
        except HTTPException:
            # Re-raise HTTPExceptions (like DB errors)
            raise
        except Exception as e:
             # Catch any other unexpected errors during parsing/validation/storage
             logger.error(f"Unexpected error during scenario processing: {str(e)}")
             logger.error(f"Stack trace: {traceback.format_exc()}")
             db.rollback() # Ensure rollback on unexpected errors
             raise HTTPException(
                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"An unexpected error occurred processing scenarios: {e}"
             )


    except openai.APIError as e:
        logger.error(f"OpenAI API error during scenario generation: {str(e)}")
        # Re-raise as HTTPException with appropriate status code based on OpenAI error
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE # Default for API errors
        if e.status_code == 400:
             status_code = status.HTTP_400_BAD_REQUEST # Bad request to OpenAI
             detail = f"AI service received a bad request: {e.message}"
        elif e.status_code == 401:
             status_code = status.HTTP_401_UNAUTHORIZED # Invalid API Key
             detail = "AI service authentication failed."
        elif e.status_code == 429:
             status_code = status.HTTP_429_TOO_MANY_REQUESTS # Rate limit
             detail = "AI service rate limit exceeded."
        elif e.status_code == 500:
             status_code = status.HTTP_502_BAD_GATEWAY # OpenAI internal error
             detail = "AI service internal error."
        else:
             detail = f"AI service error: {e.message}"

        raise HTTPException(
            status_code=status_code,
            detail=detail
        )
    except openai.APIConnectionError as e:
        logger.error(f"OpenAI API connection error during scenario generation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to AI service"
        )
    except openai.RateLimitError as e:
        logger.error(f"OpenAI API rate limit error during scenario generation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI service rate limit exceeded"
        )
    except Exception as e:
         # Catch any other unexpected errors during the OpenAI call itself
         logger.error(f"Unexpected error during OpenAI scenario generation call: {str(e)}")
         logger.error(f"Stack trace: {traceback.format_exc()}")
         raise HTTPException(
             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
             detail=f"An unexpected error occurred calling AI service: {e}"
         )


class StyleService:
    """Service for managing business communication styles and style guides."""

    async def get_training_scenarios(
        self,
        business_id: int,
        db: Session = Depends(get_db)
    ) -> Dict:
        """
        Get training scenarios for a business. If none exist, generate new ones.

        Args:
            business_id: ID of the business
            db: Database session

        Returns:
            Dict containing scenarios

        Raises:
            HTTPException: If business not found or scenario generation fails
        """
        try:
            # Verify business exists
            business = db.query(BusinessProfile).filter(
                BusinessProfile.id == business_id
            ).first()

            if not business:
                logger.warning(f"Business with id {business_id} not found.")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Business not found"
                )

            # Get existing scenarios
            scenarios = db.query(BusinessOwnerStyle).filter(
                BusinessOwnerStyle.business_id == business_id
            ).all()

            if not scenarios:
                logger.info(f"No existing scenarios for business {business_id}. Generating new ones.")
                try:
                    # generate_business_scenarios now raises HTTPException on failure,
                    # so we just call it and handle potential exceptions.
                    generated_scenarios = await generate_business_scenarios(business, db)

                    # generate_business_scenarios returns [] if no valid scenarios were generated/stored
                    if not generated_scenarios:
                         logger.warning(f"Scenario generation returned no scenarios for business {business_id}.")
                         # It's better to return an empty list than raise a 500 if generation completed without valid output
                         return {"scenarios": []}

                    logger.info(f"Generated and stored {len(generated_scenarios)} scenarios for business {business_id}")
                    return {"scenarios": generated_scenarios}
                except HTTPException:
                    # Re-raise HTTPExceptions raised by generate_business_scenarios
                    raise
                except Exception as e:
                    # Catch any other unexpected exceptions during generation call
                    logger.error(f"Unexpected error during scenario generation call for business {business_id}: {str(e)}")
                    logger.error(f"Stack trace: {traceback.format_exc()}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="An unexpected error occurred during scenario generation"
                    )

            # Format existing scenarios
            logger.info(f"Returning {len(scenarios)} existing scenarios for business {business_id}")
            return {
                "scenarios": [{
                    "id": s.id,
                    "scenario": s.scenario,
                    "context_type": s.context_type,
                    "example_response": s.response, # Use 'example_response' as per frontend need
                    "response": s.response # Keep 'response' for internal consistency if needed elsewhere
                } for s in scenarios]
            }

        except HTTPException:
            # Re-raise explicit HTTPExceptions (like 404, 503, 429, 400 from generation)
            raise
        except Exception as e:
            # Catch any other unexpected errors in this function
            logger.error(f"Unexpected error in get_training_scenarios for business {business_id}: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get scenarios due to an unexpected error"
            )


    async def analyze_owner_responses(
        self,
        responses: List[Dict],
        business: BusinessProfile
    ) -> Dict[str, Any]:
        """
        Deeply analyze business owner's responses to understand their authentic communication style.

        Args:
            responses: List of response dictionaries containing scenario, context_type, and response
            business: BusinessProfile instance

        Returns:
            Dict containing analysis results with key_phrases, style_notes, etc.

        Raises:
            HTTPException: If analysis fails due to AI issues or processing errors.
        """
        if not responses or not business:
            logger.warning("Missing required data for analysis: responses or business profile.")
            return {} # Return empty dict if no data to analyze

        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Filter out entries with empty or None responses
        valid_responses = [r for r in responses if r.get('response') is not None and r.get('response').strip() != ""]

        if not valid_responses:
             logger.info("No valid responses provided for analysis after filtering.")
             return {} # Return empty analysis if no responses are provided

        # Format only valid responses for analysis
        formatted_examples = "\n\n".join([
            f"Scenario: {r.get('scenario', 'N/A')}\nContext: {r.get('context_type', 'N/A')}\nResponse: {r.get('response', '')}"
            for r in valid_responses
        ])

        prompt = f"""
        Analyze the provided SMS responses from the business owner to create a detailed communication style guide.
        This analysis is for {business.industry} business: {business.business_name}.
        Their stated goals are: {business.business_goal}.
        Their primary services are: {business.primary_services}.

        Analyze the following RESPONSES to capture the business owner's unique voice and communication style. Focus on identifying patterns that make their communication authentic, human, and reflective of their brand personality.

        RESPONSES TO ANALYZE:
        {formatted_examples}

        Create a comprehensive analysis covering the following aspects. Focus on *how* they communicate, their typical language use, and subtle elements of their style.

        IMPORTANT: Return your analysis in this exact JSON format. It must be a single JSON object with the specified keys. Ensure the JSON is perfectly formatted, containing only the JSON object without surrounding text or markdown.
        {{
            "key_phrases": ["list of recurring or distinctive phrases"],
            "style_notes": {{
                "tone": "Describe the overall tone (e.g., friendly, professional, casual, empathetic, direct).",
                "formality_level": "Describe their formality (e.g., very formal, business casual, informal).",
                "personal_touches": ["Examples of how they add a personal touch (e.g., emojis, personal anecdotes, specific greetings)."],
                "authenticity_markers": ["What makes their voice sound authentic/human (e.g., use of slang, specific sentence structures, expression of emotion)."]
            }},
            "personality_traits": ["Inferred personality traits reflected in their writing (e.g., approachable, knowledgeable, enthusiastic, calm)."],
            "message_patterns": {{
                "greetings": ["Common ways they start messages."],
                "closings": ["Common ways they end messages (sign-offs)."],
                "transitions": ["How they transition between topics or ideas."],
                "emphasis_patterns": ["How they emphasize points (e.g., capitalization, exclamation points, sentence structure)."]
            }},
            "special_elements": {{
                "industry_terms": ["Specific jargon or terminology used related to their industry/services."],
                "metaphors": ["Any recurring metaphors or analogies."],
                "personal_references": ["How they refer to themselves or the business."],
                "emotional_markers": ["How they express or acknowledge emotions (e.g., empathy, excitement)."]
            }},
            "overall_summary": "Provide a brief paragraph summarizing the core elements of their style."
        }}

        Ensure the analysis is detailed, specific, and directly derived from the provided response examples. Avoid generic descriptions. Focus on capturing what makes their communication style UNIQUELY theirs.
        """

        try:
            logger.info(f"🧠 Analyzing owner responses for business {business.id}")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an expert in analyzing human communication patterns and personal writing styles. Generate detailed style analysis based on provided examples. Always return responses in valid JSON format, containing ONLY the JSON object. DO NOT include markdown code blocks (like ```json) or any other surrounding text."},
                    {"role": "user", "content": prompt} # Corrected key here
                ],
                temperature=0.7,
                 response_format={"type": "json_object"}
            )

            response_content = response.choices[0].message.content
            logger.info(f"Raw OpenAI analysis response: {response_content}")

            try:
                # Use robust extractor - it now just parses JSON
                analysis = robust_json_extract(response_content)

                # *** Content Validation for Analysis Output ***
                # Check if the essential keys for the style guide are present
                required_keys = ["key_phrases", "style_notes", "personality_traits", "message_patterns", "special_elements"]
                if not isinstance(analysis, dict) or not all(key in analysis for key in required_keys):
                     logger.error(f"AI analysis response structure invalid: missing required style guide keys. Content: {response_content}")
                     # Re-raise as ValueError for calling function to catch
                     raise ValueError("AI analysis response is not in the expected format or missing required style guide keys.")

                # Further validation for nested dictionaries/lists if needed
                if not isinstance(analysis.get("style_notes"), dict) or \
                   not isinstance(analysis.get("message_patterns"), dict) or \
                   not isinstance(analysis.get("special_elements"), dict) or \
                   not isinstance(analysis.get("key_phrases"), list) or \
                   not isinstance(analysis.get("personality_traits"), list):
                    logger.error(f"AI analysis response structure invalid: nested elements have wrong types. Content: {response_content}")
                    raise ValueError("AI analysis response has incorrect types for style guide elements.")


                return analysis

            except ValueError as e:
                 # Catch ValueErrors raised by robust_json_extract or content validation
                 logger.error(f"Data processing error after OpenAI analysis response: {str(e)}")
                 # Re-raise as HTTPException as this indicates a problem with the AI output processing
                 raise HTTPException(
                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                     detail=f"Failed to process style analysis response: {e}"
                 )
            except Exception as e:
                 # Catch any other unexpected errors during parsing/validation
                 logger.error(f"Unexpected error during analysis processing: {str(e)}")
                 logger.error(f"Stack trace: {traceback.format_exc()}")
                 raise HTTPException(
                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                     detail=f"An unexpected error occurred processing analysis: {e}"
                 )


        except openai.APIError as e:
            logger.error(f"OpenAI API error during analysis: {str(e)}")
            # Re-raise as HTTPException with appropriate status code
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE # Default
            if e.status_code == 400:
                 status_code = status.HTTP_400_BAD_REQUEST
                 detail = f"AI service received a bad request for analysis: {e.message}"
            elif e.status_code == 401:
                 status_code = status.HTTP_401_UNAUTHORIZED
                 detail = "AI service authentication failed for analysis."
            elif e.status_code == 429:
                 status_code = status.HTTP_429_TOO_MANY_REQUESTS
                 detail = "AI service rate limit exceeded for analysis."
            elif e.status_code == 500:
                 status_code = status.HTTP_502_BAD_GATEWAY
                 detail = "AI service internal error during analysis."
            else:
                 detail = f"AI service error during analysis: {e.message}"

            raise HTTPException(
                status_code=status_code,
                detail=detail
            )
        except openai.APIConnectionError as e:
            logger.error(f"OpenAI API connection error during analysis: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to AI service for analysis"
            )
        except openai.RateLimitError as e:
            logger.error(f"OpenAI API rate limit error during analysis: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="AI service rate limit exceeded for analysis"
            )
        except Exception as e:
             # Catch any other unexpected errors during the OpenAI call itself
             logger.error(f"Unexpected error during OpenAI analysis call: {str(e)}")
             logger.error(f"Stack trace: {traceback.format_exc()}")
             raise HTTPException(
                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"An unexpected error occurred calling AI service for analysis: {e}"
             )


    async def train_style(
        self,
        style_data: List[SMSStyleInput],
        db: Session = Depends(get_db)
    ) -> Dict:
        """
        Train business style using provided responses and analyze communication patterns.
        Updates scenario responses in the database and generates a style guide based on all
        available responses for the business that have been provided.
        """
        try:
            if not style_data:
                logger.warning("No style data provided for training.")
                return {"status": "success", "message": "No responses provided to train."}

            # Assume all style_data entries are for the same business
            business_id = style_data[0].business_id
            business = db.query(BusinessProfile).filter(
                BusinessProfile.id == business_id
            ).first()

            if not business:
                logger.warning(f"Business with id {business_id} not found for training.")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Business not found"
                )

            logger.info(f"Starting style training for business {business_id} with {len(style_data)} response updates.")

            # First, update the specific responses provided in the input
            updated_count = 0
            for data in style_data:
                # Find the scenario by scenario ID if available, otherwise by business_id and scenario text
                # Assuming scenario_id is NOT in SMSStyleInput based on original code logic
                # If SMSStyleInput *does* have scenario_id, update query to use it
                style_entry = db.query(BusinessOwnerStyle).filter(
                    BusinessOwnerStyle.business_id == data.business_id,
                    BusinessOwnerStyle.scenario == data.scenario # Using scenario text as identifier
                ).first()

                if not style_entry:
                    logger.warning(f"Scenario matching business_id {data.business_id} and scenario text '{data.scenario[:50]}...' not found for update. Skipping.")
                    continue

                style_entry.response = data.response
                # Update last_analyzed only when a non-empty response is provided
                if data.response is not None and data.response.strip() != "":
                     style_entry.last_analyzed = datetime.utcnow() # Mark this specific scenario as updated/analyzed time-wise

                db.add(style_entry) # Mark as dirty for update
                updated_count += 1

            if updated_count == 0:
                logger.warning("No matching scenarios found or updated in the database based on provided style_data.")
                # Don't rollback if no updates were attempted based on input, just return warning
                # db.rollback()
                return {"status": "warning", "message": "No matching scenarios found or updated based on input data."}

            # Commit the response updates
            try:
                 db.commit()
                 logger.info(f"Successfully updated {updated_count} scenario responses in the database.")
            except Exception as e:
                 logger.error(f"Database commit error during response updates for business {business_id}: {str(e)}")
                 db.rollback()
                 raise HTTPException(
                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                     detail="Failed to save updated responses"
                 )


            # Now, fetch ALL scenarios for this business that have responses
            all_responses_for_analysis = db.query(BusinessOwnerStyle).filter(
                BusinessOwnerStyle.business_id == business_id,
                BusinessOwnerStyle.response != "", # Only include scenarios with a response
                BusinessOwnerStyle.response is not None # Ensure response is not None
            ).all()

            if not all_responses_for_analysis:
                 logger.info(f"No scenarios with non-empty responses available for business {business_id} to generate style guide.")
                 # If no responses exist (even after updates), we can't generate a style guide.
                 # Return success for the update, but indicate no analysis was done.
                 return {
                    "status": "success",
                    "updated_count": updated_count,
                    "style_analysis": {}, # Empty analysis
                    "message": "Responses saved, but no responses provided for analysis."
                 }

            # Format these fetched scenarios for analysis
            formatted_responses_for_analysis = [{
                "scenario": s.scenario,
                "context_type": s.context_type,
                "response": s.response
            } for s in all_responses_for_analysis]

            # Analyze their communication style based on *all* provided responses
            logger.info(f"Analyzing style based on {len(formatted_responses_for_analysis)} total non-empty responses for business {business_id}.")
            # analyze_owner_responses now raises HTTPException on failure, so we call it and handle
            try:
                style_analysis = await self.analyze_owner_responses(formatted_responses_for_analysis, business)
            except HTTPException:
                 # Re-raise HTTPExceptions from analysis
                 raise
            except Exception as e:
                 # Catch unexpected errors from analysis call
                 logger.error(f"Unexpected error during analyze_owner_responses call for business {business_id}: {str(e)}")
                 logger.error(f"Stack trace: {traceback.format_exc()}")
                 raise HTTPException(
                      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                      detail=f"An unexpected error occurred during style analysis: {e}"
                 )


            # Decide where to store the style analysis.
            # Update the *most recently analyzed* entry
            # that HAS a response with the comprehensive style guide analysis.

            latest_analyzed_entry_with_response = db.query(BusinessOwnerStyle).filter(
                BusinessOwnerStyle.business_id == business_id,
                BusinessOwnerStyle.response != "",
                BusinessOwnerStyle.response is not None
            ).order_by(BusinessOwnerStyle.last_analyzed.desc()).first()


            if style_analysis and latest_analyzed_entry_with_response:
                try:
                    # Update the latest entry with the *new* analysis data.
                    latest_analyzed_entry_with_response.key_phrases = json.dumps(style_analysis.get('key_phrases', []))
                    latest_analyzed_entry_with_response.style_notes = json.dumps(style_analysis.get('style_notes', {}))
                    latest_analyzed_entry_with_response.personality_traits = json.dumps(style_analysis.get('personality_traits', []))
                    latest_analyzed_entry_with_response.message_patterns = json.dumps(style_analysis.get('message_patterns', {}))
                    latest_analyzed_entry_with_response.special_elements = json.dumps(style_analysis.get('special_elements', {}))
                    latest_analyzed_entry_with_response.overall_summary = style_analysis.get('overall_summary', '') # Store summary if added to model

                    # Update last_analyzed timestamp on this specific entry to mark the time of the *full analysis*
                    # Only update if analysis actually happened and was saved
                    latest_analyzed_entry_with_response.last_analyzed = datetime.utcnow()

                    db.add(latest_analyzed_entry_with_response) # Mark as dirty
                    db.commit()
                    logger.info(f"Successfully updated style guide analysis in DB for business {business_id} on entry ID {latest_analyzed_entry_with_response.id}.")

                except Exception as e:
                    logger.error(f"Database error while saving style analysis for business {business_id}: {str(e)}")
                    db.rollback()
                    # Log the error but don't necessarily raise HTTPException here,
                    # as responses were successfully saved. Return partial success.
                    logger.error("Failed to save style analysis to database after successful response updates.")
                    style_analysis = {} # Return empty analysis on save failure
                    # Re-fetch the updated scenarios to return their latest state
                    updated_styles_feedback = db.query(BusinessOwnerStyle).filter(
                         BusinessOwnerStyle.business_id == business_id,
                         BusinessOwnerStyle.response != "",
                         BusinessOwnerStyle.response is not None
                    ).all()
                    return {
                         "status": "warning",
                         "updated_count": updated_count,
                         "style_analysis": {}, # Return empty analysis on save failure
                         "message": "Responses saved, analysis performed, but failed to save analysis data.",
                         "updated_styles": [{
                            "scenario": s.scenario,
                            "context_type": s.context_type,
                            "response": s.response # Return the saved response
                         } for s in updated_styles_feedback]
                    }

            elif style_analysis:
                 # This case is unlikely if all_responses_for_analysis was not empty and analysis succeeded.
                 logger.warning(f"Style analysis successful for business {business_id}, but no valid DB entry found to save it to.")
                 # Return analysis but indicate save failed
                 return {
                    "status": "warning",
                    "updated_count": updated_count,
                    "style_analysis": style_analysis,
                    "message": "Responses saved, analysis performed, but failed to save analysis to database."
                 }
            else:
                 # This case means analyze_owner_responses returned empty (e.g., no valid responses, already handled)
                 logger.info(f"analyze_owner_responses returned empty analysis for business {business_id}. No style guide saved.")
                 # Return success for the response updates, but indicate no analysis
                 return {
                    "status": "success",
                    "updated_count": updated_count,
                    "style_analysis": {},
                    "message": "Responses saved, but no analysis performed (insufficient response data)."
                 }


            # Re-fetch the updated scenarios to return their latest state after potential analysis commit
            # We should return the list of scenarios with their updated responses
            updated_scenarios_with_responses = db.query(BusinessOwnerStyle).filter(
                 BusinessOwnerStyle.business_id == business_id,
                 BusinessOwnerStyle.response != "", # Or return all scenarios? Let's return those with responses
                 BusinessOwnerStyle.response is not None
            ).all()


            # Return formatted response including the analysis results and updated scenarios
            return {
                "status": "success",
                "updated_count": updated_count,
                "style_analysis": style_analysis if style_analysis else {}, # Ensure style_analysis is not None
                "updated_styles": [{ # Renamed from updated_styles to clarify these are scenarios with responses
                    "id": s.id, # Include ID here for client side tracking
                    "scenario": s.scenario,
                    "context_type": s.context_type,
                    "response": s.response # Return the saved response
                } for s in updated_scenarios_with_responses]
            }

        except HTTPException:
            # Re-raise explicit HTTPExceptions
            raise
        except Exception as e:
            logger.error(f"Unexpected error in train_style for business {business_id}: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            db.rollback() # Ensure rollback on unexpected errors
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to train style due to an unexpected error"
            )

    async def analyze_style(
        self,
        business_id: int,
        message: str,
        db: Session = Depends(get_db)
    ) -> Dict[str, any]:
        """
        Analyze message against business style.

        Args:
            business_id: ID of the business
            message: Message to analyze
            db: Database session

        Returns:
            Dictionary containing analysis results

        Raises:
            HTTPException: If style guide not found or analysis fails
        """
        try:
            # Get the latest style guide data stored for the business.
            # This is assumed to be stored in the BusinessOwnerStyle entry
            # that was most recently updated during a training process
            # and has analysis data populated.
            style_guide_entry = db.query(BusinessOwnerStyle).filter(
                BusinessOwnerStyle.business_id == business_id,
                BusinessOwnerStyle.style_notes is not None # Ensure analysis data exists
            ).order_by(BusinessOwnerStyle.last_analyzed.desc()).first()

            if not style_guide_entry:
                 logger.warning(f"No complete style guide found for business {business_id} for analysis.")
                 raise HTTPException(
                     status_code=status.HTTP_404_NOT_FOUND,
                     detail="No complete style guide found for this business. Please train the style first."
                 )

            # Prepare style guide data for the AI model
            style_guide_data: Dict[str, Any] = {}
            try:
                # Use standard json.loads here as DB data *should* be reliable and already validated/cleaned on save
                key_phrases = json.loads(style_guide_entry.key_phrases) if style_guide_entry.key_phrases else []
                style_notes = json.loads(style_guide_entry.style_notes) if style_guide_entry.style_notes else {}
                personality_traits = json.loads(style_guide_entry.personality_traits) if style_guide_entry.personality_traits else []
                message_patterns = json.loads(style_guide_entry.message_patterns) if style_guide_entry.message_patterns else {}
                special_elements = json.loads(style_guide_entry.special_elements) if style_guide_entry.special_elements else {}
                overall_summary = style_guide_entry.overall_summary if hasattr(style_guide_entry, 'overall_summary') and style_guide_entry.overall_summary else ""


                # Also get business profile details for context in prompt
                business = db.query(BusinessProfile).filter(
                    BusinessProfile.id == business_id
                ).first()

                if not business:
                     # This should ideally not happen if style_guide_entry exists and is linked
                     logger.error(f"Associated business profile {business_id} not found for style analysis.")
                     raise HTTPException(
                         status_code=status.HTTP_404_NOT_FOUND, # Or 500 if data integrity issue
                         detail="Associated business profile not found."
                     )


            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON style guide data for business {business_id} from DB: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to load business style guide data from database."
                )


            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            prompt = f"""
            Analyze the following message against the provided communication style guide for {business.business_name}, a {business.industry} business.
            Determine how well the message matches the established style and provide specific feedback.

            BUSINESS COMMUNICATION STYLE GUIDE:
            {json.dumps(style_guide_data, indent=2)}

            MESSAGE TO ANALYZE:
            "{message}"

            Evaluate the message based on the style guide's key phrases, tone, formality, personal touches, personality traits, message patterns (greetings, closings), and special elements.

            IMPORTANT: Return your analysis in this exact JSON format. Ensure the JSON is perfectly formatted, containing only the JSON object without surrounding text or markdown.
            {{
                "matches_style": true | false,
                "confidence": "high" | "medium" | "low",
                "suggestions": ["List specific suggestions to improve style match, if needed."],
                "key_phrases_found": ["List key phrases from the style guide found in the message."],
                "style_elements_present": ["List style elements (tone, formality, personal touches, etc.) observed in the message."],
                "analysis_notes": "Brief explanation of the analysis."
            }}
            """

            try:
                 logger.info(f"🔬 Analyzing message against style guide for business {business_id}")
                 response = client.chat.completions.create(
                     model="gpt-4o",
                     messages=[
                         {"role": "system", "content": "You are an expert in analyzing text against a predefined communication style guide. Provide detailed feedback on how well a given message matches the style. Always return responses in valid JSON format, containing ONLY the JSON object. DO NOT include markdown code blocks (like ```json) or any other surrounding text."},
                         {"role": "user", "content": prompt} # Corrected key here
                     ],
                     temperature=0.5,
                     response_format={"type": "json_object"}
                 )

                 response_content = response.choices[0].message.content
                 logger.info(f"Raw OpenAI style analysis result response: {response_content}")

                 try:
                    # Use robust extractor - it now just parses JSON
                    analysis_result = robust_json_extract(response_content)

                    # *** Content Validation for Analysis Result Output ***
                    required_result_keys = ["matches_style", "confidence", "suggestions", "key_phrases_found", "style_elements_present", "analysis_notes"]
                    if not isinstance(analysis_result, dict) or not all(key in analysis_result for key in required_result_keys):
                         logger.error(f"AI analysis result structure invalid: missing required result keys. Content: {response_content}")
                         # Re-raise as ValueError for calling function to catch
                         raise ValueError("AI analysis result is not in the expected format or missing required keys.")

                    # Further type validation if necessary
                    if not isinstance(analysis_result.get("matches_style"), bool) or \
                       not isinstance(analysis_result.get("confidence"), str) or \
                       not isinstance(analysis_result.get("suggestions"), list) or \
                       not isinstance(analysis_result.get("key_phrases_found"), list) or \
                       not isinstance(analysis_result.get("style_elements_present"), list) or \
                       not isinstance(analysis_result.get("analysis_notes"), str):
                         logger.error(f"AI analysis result structure invalid: values have wrong types. Content: {response_content}")
                         raise ValueError("AI analysis result has incorrect value types.")


                    return analysis_result

                 except ValueError as e:
                      # Catch ValueErrors raised by robust_json_extract or content validation
                      logger.error(f"Data processing error after OpenAI analysis result response: {str(e)}")
                      # Re-raise as HTTPException
                      raise HTTPException(
                          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail=f"Failed to process style analysis result: {e}"
                      )
                 except Exception as e:
                      # Catch any other unexpected errors during parsing/validation
                      logger.error(f"Unexpected error during analysis result processing: {str(e)}")
                      logger.error(f"Stack trace: {traceback.format_exc()}")
                      raise HTTPException(
                          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail=f"An unexpected error occurred processing analysis result: {e}"
                      )


            except openai.APIError as e:
                logger.error(f"OpenAI API error during style analysis call: {str(e)}")
                # Re-raise as HTTPException with appropriate status code
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE # Default
                if e.status_code == 400:
                     status_code = status.HTTP_400_BAD_REQUEST
                     detail = f"AI service received a bad request for style analysis: {e.message}"
                elif e.status_code == 401:
                     status_code = status.HTTP_401_UNAUTHORIZED
                     detail = "AI service authentication failed for style analysis."
                elif e.status_code == 429:
                     status_code = status.HTTP_429_TOO_MANY_REQUESTS
                     detail = "AI service rate limit exceeded for style analysis."
                elif e.status_code == 500:
                     status_code = status.HTTP_502_BAD_GATEWAY
                     detail = "AI service internal error during style analysis."
                else:
                     detail = f"AI service error during style analysis: {e.message}"

                raise HTTPException(
                    status_code=status_code,
                    detail=detail
                )
            except openai.APIConnectionError as e:
                logger.error(f"OpenAI API connection error during style analysis call: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Could not connect to AI service for style analysis"
                )
            except openai.RateLimitError as e:
                logger.error(f"OpenAI API rate limit error during style analysis call: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="AI service rate limit exceeded for style analysis"
                )
            except Exception as e:
                # Catch any other unexpected errors during the OpenAI call itself
                logger.error(f"Unexpected error during OpenAI style analysis call: {str(e)}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"An unexpected error occurred calling AI service for style analysis: {e}"
                )

        except HTTPException:
            # Re-raise explicit HTTPExceptions (like 404, from AI call)
            raise
        except Exception as e:
            # Catch any other unexpected errors in this function
            logger.error(f"Unexpected error in analyze_style for business {business_id}: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to analyze style due to an unexpected error"
            )


    async def get_style_guide(
        self,
        business_id: int,
        db: Session = Depends(get_db)
    ) -> Dict:
        """
        Get current style guide for a business.
        The style guide is stored in the most recently analyzed BusinessOwnerStyle entry.

        Args:
            business_id: ID of the business
            db: Database session

        Returns:
            Dictionary containing the style guide data

        Raises:
            HTTPException: If style guide not found or retrieval fails
        """
        try:
            # Find the BusinessOwnerStyle entry that holds the style guide data.
            # This is assumed to be the most recently updated/analyzed one that has style_notes.
            style_entry = db.query(BusinessOwnerStyle).filter(
                BusinessOwnerStyle.business_id == business_id,
                BusinessOwnerStyle.style_notes is not None # Ensure analysis data exists
            ).order_by(BusinessOwnerStyle.last_analyzed.desc()).first()

            if not style_entry:
                 logger.warning(f"No style guide data found for business {business_id}.")
                 raise HTTPException(
                     status_code=status.HTTP_404_NOT_FOUND,
                     detail="No style guide found for this business. Please train the style first."
                 )

            # Attempt to parse the JSON fields
            try:
                # Use standard json.loads here as DB data *should* be reliable and already validated/cleaned on save
                key_phrases = json.loads(style_entry.key_phrases) if style_entry.key_phrases else []
                style_notes = json.loads(style_entry.style_notes) if style_entry.style_notes else {}
                personality_traits = json.loads(style_entry.personality_traits) if style_entry.personality_traits else []
                message_patterns = json.loads(style_entry.message_patterns) if style_entry.message_patterns else {}
                special_elements = json.loads(style_entry.special_elements) if style_entry.special_elements else {}
                overall_summary = style_entry.overall_summary if hasattr(style_entry, 'overall_summary') and style_entry.overall_summary else ""


            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON style guide data for business {business_id} from DB: {e}")
                # If JSON is malformed in DB, it's a server error.
                raise HTTPException(
                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                     detail="Failed to parse business style guide data from database."
                )


            return {
                "id": style_entry.id,
                "business_id": style_entry.business_id,
                "key_phrases": key_phrases,
                "style_notes": style_notes,
                "personality_traits": personality_traits,
                "message_patterns": message_patterns,
                "special_elements": special_elements,
                "overall_summary": overall_summary,
                "last_analyzed": style_entry.last_analyzed.isoformat() if style_entry.last_analyzed else None
            }

        except HTTPException:
            # Re-raise explicit HTTPExceptions (like 404, 500)
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_style_guide for business {business_id}: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get style guide due to an unexpected error"
            )


    async def update_scenario_response(
        self,
        scenario_id: int,
        business_id: int,
        response: str,
        db: Session = Depends(get_db)
    ) -> Dict:
        """
        Update a specific scenario with the business owner's response.
        This is a focused update for a single scenario response.
        Training/analysis (which uses ALL responses) happens separately via train_style.

        Args:
            scenario_id: ID of the scenario
            business_id: ID of the business
            response: Business owner's response
            db: Database session

        Returns:
            Dictionary containing the updated scenario data

        Raises:
            HTTPException: If scenario not found or update fails
        """
        try:
            # Find the specific scenario by its ID and business ID
            scenario = db.query(BusinessOwnerStyle).filter(
                BusinessOwnerStyle.id == scenario_id,
                BusinessOwnerStyle.business_id == business_id
            ).first()

            if not scenario:
                 logger.warning(f"Scenario with id {scenario_id} not found for business {business_id} for update.")
                 raise HTTPException(
                     status_code=status.HTTP_404_NOT_FOUND,
                     detail="Scenario not found"
                 )

            # Update the response field
            scenario.response = response
            # Update last_analyzed timestamp on this entry
            scenario.last_analyzed = datetime.utcnow()


            db.add(scenario) # Mark as dirty
            db.commit()
            db.refresh(scenario) # Refresh to get the latest state after commit

            logger.info(f"Successfully updated response for scenario {scenario_id} for business {business_id}.")

            return {
                "id": scenario.id,
                "business_id": scenario.business_id,
                "scenario": scenario.scenario,
                "context_type": scenario.context_type,
                "response": scenario.response,
                "last_analyzed": scenario.last_analyzed.isoformat() if scenario.last_analyzed else None
                # Include other fields if needed by the frontend after update
                # "key_phrases": json.loads(scenario.key_phrases) if scenario.key_phrases else [],
                # ... other style guide fields ...
            }

        except Exception as e:
            logger.error(f"Error updating scenario response for scenario {scenario_id}, business {business_id}: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            db.rollback() # Ensure rollback on error
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update scenario response"
            )
        
    async def learn_from_edit(
        self,
        original: str,
        edited: str,
        business_id: int,
        db: Session
    ) -> dict:
        """
        Learn from manual edits to improve style understanding.
        Updates the style guide with new learnings from the edit.
        """
        logger.info(f"Learning from edit for business {business_id}")
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        prompt = f"""
        Analyze how this message was edited to improve style matching:

        Original: {original}
        Edited: {edited}

        What specific changes were made to better match the owner's voice?
        Return as JSON with these keys:
        1. added_elements: What was added to improve authenticity
        2. removed_elements: What was removed that didn't match their voice
        3. structural_changes: How the message structure was modified
        4. tone_adjustments: How the tone was adjusted
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}]
        )

        changes = json.loads(response.choices[0].message.content)

        # Update style guide with new learnings
        style_guide = db.query(BusinessOwnerStyle).filter(
            BusinessOwnerStyle.business_id == business_id
        ).first()

        if style_guide:
            current_notes = json.loads(style_guide.style_notes) if style_guide.style_notes else {}
            current_notes['learned_from_edits'] = current_notes.get('learned_from_edits', [])
            current_notes['learned_from_edits'].append(changes)
            style_guide.style_notes = json.dumps(current_notes)
            db.commit()
            logger.info(f"Updated style guide with learnings from edit for business {business_id}")

        return changes

# Backward-compatible function for learn_from_edit
async def learn_from_edit(original: str, edited: str, business_id: int, db: Session):
    service = StyleService()
    return await service.learn_from_edit(original, edited, business_id, db)

async def get_style_guide(business_id: int, db: Session):
    """
    Backward-compatible function for legacy imports.
    """
    service = StyleService()
    return await service.get_style_guide(business_id, db)
    
