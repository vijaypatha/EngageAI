# backend/app/services/copilot_nudge_generation_service.py
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, Integer
from datetime import datetime, timedelta, timezone # Added timezone
from typing import Optional, Dict, Any, List, Literal
import re
import sqlalchemy as sa
import json

import openai 
from app.config import settings 

from app.models import (
    CoPilotNudge,
    Message,
    Customer,
    BusinessProfile,
    NudgeTypeEnum,
    NudgeStatusEnum,
    MessageTypeEnum,
)
from app.schemas import CoPilotNudgeCreate

logger = logging.getLogger(__name__)

class CoPilotNudgeGenerationService:
    def __init__(self, db: Session):
        self.db = db
        if settings.OPENAI_API_KEY:
            try:
                self.openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                logger.info("[Service Init] OpenAI client initialized successfully.")
            except Exception as e:
                logger.error(f"[Service Init] Error initializing OpenAI client: {e}", exc_info=True)
                self.openai_client = None
        else:
            logger.warning("[Service Init] OPENAI_API_KEY not found. Strategic plan generation will be unavailable.")
            self.openai_client = None

    def detect_positive_sentiment_and_create_nudges(self, business_id: int) -> list[CoPilotNudge]:
        """
        Detects positive sentiment in recent messages and creates CoPilotNudge records.
        """
        logger.info(f"Detecting positive sentiment for CoPilotNudges for business ID: {business_id}")
        
        positive_keywords = ["love", "amazing", "great", "excellent", "fantastic", "wonderful", "happy", "pleased", "satisfied", "thank you", "thanks"]
        time_threshold = datetime.now(timezone.utc) - timedelta(days=7)

        recent_messages = self.db.query(Message).filter(
            Message.business_id == business_id,
            Message.created_at >= time_threshold,
            Message.message_type == MessageTypeEnum.INBOUND.value
        ).all()

        created_nudges = []
        for message in recent_messages:
            if any(keyword in message.content.lower() for keyword in positive_keywords):
                existing_nudge = self.db.query(CoPilotNudge).filter(
                    CoPilotNudge.nudge_type == NudgeTypeEnum.SENTIMENT_POSITIVE,
                    CoPilotNudge.ai_evidence_snippet.op('->>')('original_message_id').cast(sa.Integer) == message.id
                ).first()

                if existing_nudge:
                    logger.info(f"Positive sentiment nudge for message {message.id} already exists. Skipping.")
                    continue
                
                logger.info(f"Found positive sentiment in message {message.id}.")
                nudge = CoPilotNudge(
                    business_id=business_id,
                    customer_id=message.customer_id,
                    nudge_type=NudgeTypeEnum.SENTIMENT_POSITIVE,
                    status=NudgeStatusEnum.ACTIVE,
                    message_snippet=message.content[:255],
                    ai_suggestion="This customer expressed positive sentiment! Consider asking for a review.",
                    ai_evidence_snippet={"original_message_id": message.id, "text": message.content}
                )
                self.db.add(nudge)
                created_nudges.append(nudge)
        
        if created_nudges:
            self.db.commit()
            logger.info(f"Successfully created {len(created_nudges)} positive sentiment nudges.")
        else:
            logger.info("No new positive sentiment detected.")
        return created_nudges

    def detect_potential_timed_commitments(self, business_id: int, specific_message_id: Optional[int] = None) -> list[CoPilotNudge]:
        """
        Detects potential timed commitments from recent messages.
        This version has improved, more lenient detection logic.
        """
        logger.info(f"[Service] Detecting potential timed commitments for Business ID: {business_id}")

        commitment_keywords = ["schedule", "appointment", "book", "set up a time", "meet on", "available on"]
        time_signal_keywords = ["morning", "afternoon", "evening", "next week", "tomorrow", "today", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "am", "pm"]
        
        query = self.db.query(Message).filter(
            Message.business_id == business_id,
            Message.message_type == MessageTypeEnum.INBOUND.value,
            Message.created_at >= datetime.now(timezone.utc) - timedelta(days=2)
        )
        if specific_message_id:
            query = query.filter(Message.id == specific_message_id)
        
        messages_to_analyze = query.all()
        created_nudges = []

        for message in messages_to_analyze:
            content_lower = message.content.lower()
            if any(kw in content_lower for kw in commitment_keywords) and any(kw in content_lower for kw in time_signal_keywords):
                logger.info(f"[Service] Potential timed commitment FOUND in Message ID {message.id}.")
                
                existing_nudge = self.db.query(CoPilotNudge).filter(
                    CoPilotNudge.nudge_type == NudgeTypeEnum.POTENTIAL_TARGETED_EVENT,
                    CoPilotNudge.ai_evidence_snippet.op('->>')('original_message_id').cast(sa.Integer) == message.id
                ).first()

                if existing_nudge:
                    logger.info(f"Event nudge for message {message.id} already exists. Skipping.")
                    continue

                nudge = CoPilotNudge(
                    business_id=business_id,
                    customer_id=message.customer_id,
                    nudge_type=NudgeTypeEnum.POTENTIAL_TARGETED_EVENT,
                    status=NudgeStatusEnum.ACTIVE,
                    message_snippet=message.content[:255],
                    ai_suggestion="This customer mentioned scheduling. Would you like to create a Targeted Event?",
                    ai_evidence_snippet={"original_message_id": message.id, "text": message.content}
                )
                self.db.add(nudge)
                created_nudges.append(nudge)
        
        if created_nudges:
            self.db.commit()
            logger.info(f"Successfully created {len(created_nudges)} potential timed commitment nudges.")
        else:
            logger.info("No new potential timed commitments detected.")
        return created_nudges

    def generate_strategic_engagement_plan(self, business_id: int, customer_id: int, trigger_type: Literal["nuanced_sms"], trigger_data: Dict[str, Any]) -> Optional[CoPilotNudge]:
        """
        Generates a STRATEGIC_ENGAGEMENT_OPPORTUNITY nudge using the full LLM logic.
        """
        log_prefix = f"[Service][StrategicPlanGen B:{business_id} C:{customer_id}]"
        logger.info(f"{log_prefix} Starting generation for trigger: {trigger_type}")

        if not self.openai_client:
            logger.error(f"{log_prefix} OpenAI client not initialized.")
            return None

        business = self.db.get(BusinessProfile, business_id)
        customer = self.db.get(Customer, customer_id)
        if not business or not customer:
            logger.warning(f"{log_prefix} Business or Customer not found.")
            return None

        customer_details = { "name": customer.customer_name, "lifecycle_stage": customer.lifecycle_stage, "pain_points": customer.pain_points, "interaction_history_summary": customer.interaction_history }
        business_details = { "name": business.business_name, "industry": business.industry, "primary_services": business.primary_services, "overall_goal": business.business_goal, "representative_name": business.representative_name or business.business_name }
        
        prompt = f"""
        You are an expert SMS engagement strategist. Create a short (1-3 messages) SMS engagement plan.
        Business Profile: {json.dumps(business_details, indent=2)}
        Customer Profile: {json.dumps(customer_details, indent=2)}
        Triggering Context: Customer '{customer.customer_name}' replied '{trigger_data.get("customer_reply")}' to your message '{trigger_data.get("last_business_message")}'.
        Desired Business Objective: Nurture this lead and clarify their interest.
        Instructions:
        1. Draft 1 to 3 concise SMS messages (max 160 chars, ending with "- {business_details['representative_name']}").
        2. Provide a "plan_objective" string.
        3. Provide a "reason_to_believe" string.
        Output strictly in the following JSON format:
        {{
          "plan_objective": "Your concise objective.",
          "reason_to_believe": "Your rationale for the business owner.",
          "messages": [
            {{ "text": "SMS message 1 text...", "suggested_delay_description": "Timing for message 1" }},
            {{ "text": "SMS message 2 text...", "suggested_delay_description": "Timing for message 2" }}
          ]
        }}
        """
        
        try:
            completion = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "You are an expert SMS engagement strategist."}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            llm_response_content = completion.choices[0].message.content
            parsed_plan_payload = json.loads(llm_response_content)

            nudge = CoPilotNudge(
                business_id=business_id,
                customer_id=customer_id,
                nudge_type=NudgeTypeEnum.STRATEGIC_ENGAGEMENT_OPPORTUNITY,
                status=NudgeStatusEnum.ACTIVE,
                message_snippet=trigger_data.get("customer_reply", "Recent interaction")[:255],
                ai_suggestion=f"AI suggests a plan to '{parsed_plan_payload.get('plan_objective', 'engage this customer')}'.",
                ai_evidence_snippet=trigger_data, 
                ai_suggestion_payload=parsed_plan_payload
            )
            self.db.add(nudge)
            self.db.commit()
            self.db.refresh(nudge)
            logger.info(f"{log_prefix} Successfully created STRATEGIC_ENGAGEMENT_OPPORTUNITY Nudge ID: {nudge.id}")
            return nudge
        except Exception as e:
            logger.error(f"{log_prefix} Error during OpenAI call or processing: {e}", exc_info=True)
            self.db.rollback()
            return None

    def detect_negative_sentiment_and_create_nudges(self, business_id: int) -> list[CoPilotNudge]:
        """
        Detects negative sentiment in recent messages and creates CoPilotNudge records.
        """
        logger.info(f"Detecting negative sentiment for CoPilotNudges for business ID: {business_id}")
        
        negative_keywords = ["unhappy", "problem", "issue", "not satisfied", "bad", "terrible", "disappointed", "poor", "error", "complaint", "fix this", "refund", "broken", "doesn't work"]
        time_threshold = datetime.now(timezone.utc) - timedelta(days=7)

        recent_messages = self.db.query(Message).filter(
            Message.business_id == business_id,
            Message.created_at >= time_threshold,
            Message.message_type == MessageTypeEnum.INBOUND.value
        ).all()

        created_nudges = []
        for message in recent_messages:
            if any(keyword in message.content.lower() for keyword in negative_keywords):
                existing_nudge = self.db.query(CoPilotNudge).filter(
                    CoPilotNudge.nudge_type == NudgeTypeEnum.SENTIMENT_NEGATIVE,
                    CoPilotNudge.ai_evidence_snippet.op('->>')('original_message_id').cast(sa.Integer) == message.id
                ).first()

                if existing_nudge:
                    continue

                logger.info(f"Found negative sentiment in message {message.id}.")
                nudge = CoPilotNudge(
                    business_id=business_id,
                    customer_id=message.customer_id,
                    nudge_type=NudgeTypeEnum.SENTIMENT_NEGATIVE,
                    status=NudgeStatusEnum.ACTIVE,
                    message_snippet=message.content[:255],
                    ai_suggestion="This customer expressed negative sentiment. Review the conversation and consider how to address their concerns.",
                    ai_evidence_snippet={"original_message_id": message.id, "text": message.content}
                )
                self.db.add(nudge)
                created_nudges.append(nudge)
        
        if created_nudges:
            self.db.commit()
            logger.info(f"Successfully created {len(created_nudges)} negative sentiment nudges.")
        else:
            logger.info("No new negative sentiment detected.")
        return created_nudges
