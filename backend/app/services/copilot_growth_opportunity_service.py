# backend/app/services/copilot_growth_opportunity_service.py
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, text
from datetime import datetime, timedelta, timezone # Added timezone
from typing import List, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import joinedload

from app.models import (
    CoPilotNudge,
    Customer,
    TargetedEvent,
    NudgeTypeEnum,
    NudgeStatusEnum,
    BusinessProfile,
    RoadmapMessage,
    MessageStatusEnum,
)
from app.schemas import CoPilotNudgeCreate

logger = logging.getLogger(__name__)

class CoPilotGrowthOpportunityService:
    """
    Service dedicated to identifying proactive, long-term growth opportunities
    by analyzing customer data beyond single conversations.
    """

    def __init__(self, db: Session):
        """
        Initializes the service with a database session.

        Args:
            db (Session): The SQLAlchemy database session.
        """
        self.db = db

    def identify_referral_opportunities(self, business_id: int) -> List[CoPilotNudge]:
        """
        Identifies highly satisfied customers who could be candidates for a referral campaign.

        Criteria for a "happy customer":
        - Has had a positive sentiment nudge in the last 30 days.
        - Has a completed TargetedEvent (appointment/service) in the last 60 days.
        - Does not have an active or recently actioned referral nudge.

        Args:
            business_id (int): The ID of the business to analyze.

        Returns:
            List[CoPilotNudge]: A list of newly created referral opportunity nudges.
        """
        log_prefix = f"[GrowthSvc-Referral B:{business_id}]"
        logger.info(f"{log_prefix} Starting referral opportunity analysis.")

        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        sixty_days_ago = datetime.now(timezone.utc) - timedelta(days=60)

        # Find customers with recent positive sentiment
        happy_customers_query = self.db.query(CoPilotNudge.customer_id).filter(
            CoPilotNudge.business_id == business_id,
            CoPilotNudge.nudge_type == NudgeTypeEnum.SENTIMENT_POSITIVE,
            CoPilotNudge.created_at >= thirty_days_ago
        ).distinct()

        # Find customers with recently completed events
        serviced_customers_query = self.db.query(TargetedEvent.customer_id).filter(
            TargetedEvent.business_id == business_id,
            TargetedEvent.status == 'Completed', # Assuming 'Completed' status exists
            TargetedEvent.event_datetime_utc >= sixty_days_ago
        ).distinct()
        
        # Find customers who are in both lists
        happy_customer_ids = {row[0] for row in happy_customers_query.all()}
        serviced_customer_ids = {row[0] for row in serviced_customers_query.all()}
        
        target_customer_ids = list(happy_customer_ids.intersection(serviced_customer_ids))

        if not target_customer_ids:
            logger.info(f"{log_prefix} No customers met the criteria for a new referral campaign.")
            return []

        # Exclude customers who are part of an existing, recent referral nudge
        existing_nudge_customers_query = self.db.query(CoPilotNudge.ai_suggestion_payload).filter(
            CoPilotNudge.business_id == business_id,
            CoPilotNudge.nudge_type == NudgeTypeEnum.GOAL_OPPORTUNITY,
            CoPilotNudge.status.in_([NudgeStatusEnum.ACTIVE, NudgeStatusEnum.ACTIONED]),
            CoPilotNudge.created_at >= thirty_days_ago,
            text("ai_suggestion_payload->>'opportunity_type' = 'REFERRAL_CAMPAIGN'")
        )

        customers_in_existing_nudges = set()
        for payload in existing_nudge_customers_query.all():
            if payload and payload[0] and 'customer_ids' in payload[0]:
                customers_in_existing_nudges.update(payload[0]['customer_ids'])
        
        final_customer_ids = [cid for cid in target_customer_ids if cid not in customers_in_existing_nudges]

        if not final_customer_ids:
            logger.info(f"{log_prefix} All potential referral candidates are already in recent campaigns.")
            return []

        business = self.db.get(BusinessProfile, business_id)
        num_customers = len(final_customer_ids)
        customer_word = "customer" if num_customers == 1 else "customers"

        # Create a single nudge for this campaign
        nudge = CoPilotNudge(
            business_id=business_id,
            customer_id=None,  # This nudge is not for a single customer
            nudge_type=NudgeTypeEnum.GOAL_OPPORTUNITY,
            status=NudgeStatusEnum.ACTIVE,
            message_snippet=f"You have {num_customers} happy {customer_word} who recently completed their service.",
            ai_suggestion="Launch a referral campaign to this group to drive word-of-mouth growth.",
            ai_suggestion_payload={
                "opportunity_type": "REFERRAL_CAMPAIGN",
                "customer_ids": final_customer_ids,
                "draft_message": f"Hi {{customer_name}}, we're so glad you had a great experience with us! As a thank you, we'd like to offer you [YOUR_OFFER] for any friend you refer. Thanks, {business.representative_name or business.business_name}"
            }
        )
        
        self.db.add(nudge)
        self.db.commit()
        self.db.refresh(nudge)
        
        logger.info(f"{log_prefix} Successfully created Referral Campaign Nudge ID {nudge.id} for {num_customers} customers.")
        return [nudge]
    
    async def launch_growth_campaign_from_nudge(self, nudge_id: int, business_id_from_auth: int) -> Dict[str, Any]:
        """
        MODIFIED: Creates draft engagement plan messages from a GOAL_OPPORTUNITY nudge
        instead of sending them directly.

        - Validates the nudge.
        - Creates RoadmapMessage records in a 'pending_review' state.
        - Updates the nudge status to ACTIONED.
        """
        log_prefix = f"[GrowthSvc-CreateDraft B:{business_id_from_auth} N:{nudge_id}]"
        logger.info(f"{log_prefix} Received request to create draft campaign from nudge.")

        nudge = self.db.query(CoPilotNudge).options(
            joinedload(CoPilotNudge.business)
        ).filter(
            CoPilotNudge.id == nudge_id,
            CoPilotNudge.business_id == business_id_from_auth
        ).first()

        if not nudge:
            logger.warning(f"{log_prefix} Nudge not found or business mismatch.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nudge not found.")

        if nudge.status != NudgeStatusEnum.ACTIVE.value:
            logger.warning(f"{log_prefix} Nudge is not active (status: {nudge.status}).")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Nudge is not active, it has status '{nudge.status}'.")

        if nudge.nudge_type != NudgeTypeEnum.GOAL_OPPORTUNITY.value:
            logger.warning(f"{log_prefix} Nudge is not a goal opportunity nudge.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This action is only for goal opportunity nudges.")

        payload = nudge.ai_suggestion_payload or {}
        customer_ids = payload.get("customer_ids", [])
        draft_message_template = payload.get("draft_message")

        if not customer_ids or not draft_message_template:
            logger.error(f"{log_prefix} Nudge payload is missing 'customer_ids' or 'draft_message'.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nudge data is incomplete and cannot be actioned.")

        customers_to_message = self.db.query(Customer).filter(
            Customer.id.in_(customer_ids),
            Customer.business_id == business_id_from_auth
        ).all()
        
        if len(customers_to_message) != len(customer_ids):
             logger.warning(f"{log_prefix} Some customer IDs were not found or did not belong to the business.")

        drafts_created_count = 0
        default_send_time = datetime.now(timezone.utc) + timedelta(days=1)

        for customer in customers_to_message:
            personalized_message = draft_message_template.replace('{customer_name}', customer.customer_name or 'there')
            
            new_draft = RoadmapMessage(
                business_id=business_id_from_auth,
                customer_id=customer.id,
                smsContent=personalized_message,
                status=MessageStatusEnum.PENDING_REVIEW.value,
                send_datetime_utc=default_send_time,
                smsTiming='{"source": "Co-Pilot Growth Draft"}',
                relevance="Draft created from Co-Pilot growth opportunity.",
            )
            self.db.add(new_draft)
            drafts_created_count += 1
        
        nudge.status = NudgeStatusEnum.ACTIONED.value
        nudge.updated_at = datetime.now(timezone.utc)
        self.db.add(nudge)

        self.db.commit()
        logger.info(f"{log_prefix} Successfully created {drafts_created_count} drafts. Nudge status set to ACTIONED.")

        return {"drafts_created": drafts_created_count, "message": f"{drafts_created_count} campaign drafts created successfully."}

    def identify_re_engagement_opportunities(self, business_id: int) -> List[CoPilotNudge]:
        """
        Identifies previously high-value customers who have become inactive.

        Criteria for a "high-value, inactive customer":
        - Has at least 2 completed TargetedEvents in their history.
        - Has had no inbound or outbound messages in the last 90 days.
        - Is not part of an active or recent re-engagement campaign nudge.
        
        Args:
            business_id (int): The ID of the business to analyze.

        Returns:
            List[CoPilotNudge]: A list of newly created re-engagement opportunity nudges.
        """
        log_prefix = f"[GrowthSvc-ReEngage B:{business_id}]"
        logger.info(f"{log_prefix} Starting re-engagement opportunity analysis.")

        ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
        
        # Find customers with 2 or more completed events ever
        high_value_customers_query = self.db.query(
            TargetedEvent.customer_id, 
            func.count(TargetedEvent.id).label('event_count')
        ).filter(
            TargetedEvent.business_id == business_id,
            TargetedEvent.status == 'Completed'
        ).group_by(TargetedEvent.customer_id).having(func.count(TargetedEvent.id) >= 2)

        high_value_customer_ids = {row[0] for row in high_value_customers_query.all()}
        
        if not high_value_customer_ids:
            logger.info(f"{log_prefix} No high-value customers found.")
            return []

        # Find customers with recent messages (to exclude them)
        recent_message_customers_query = self.db.query(
            CoPilotNudge.customer_id
        ).filter(
            CoPilotNudge.business_id == business_id,
            CoPilotNudge.customer_id.in_(high_value_customer_ids),
            CoPilotNudge.created_at >= ninety_days_ago
        ).distinct()
        
        active_customer_ids = {row[0] for row in recent_message_customers_query.all()}
        
        # Get the final list of inactive customers
        inactive_customer_ids = list(high_value_customer_ids - active_customer_ids)

        if not inactive_customer_ids:
            logger.info(f"{log_prefix} No high-value customers have become inactive.")
            return []
            
        # Exclude customers who are part of an existing, recent re-engagement nudge
        existing_nudge_customers_query = self.db.query(CoPilotNudge.ai_suggestion_payload).filter(
            CoPilotNudge.business_id == business_id,
            CoPilotNudge.nudge_type == NudgeTypeEnum.GOAL_OPPORTUNITY,
            CoPilotNudge.status.in_([NudgeStatusEnum.ACTIVE, NudgeStatusEnum.ACTIONED]),
            CoPilotNudge.created_at >= ninety_days_ago,
            text("ai_suggestion_payload->>'opportunity_type' = 'RE_ENGAGEMENT_CAMPAIGN'")
        )

        customers_in_existing_nudges = set()
        for payload in existing_nudge_customers_query.all():
            if payload and payload[0] and 'customer_ids' in payload[0]:
                customers_in_existing_nudges.update(payload[0]['customer_ids'])
        
        final_customer_ids = [cid for cid in inactive_customer_ids if cid not in customers_in_existing_nudges]

        if not final_customer_ids:
            logger.info(f"{log_prefix} All potential re-engagement candidates are already in recent campaigns.")
            return []

        business = self.db.get(BusinessProfile, business_id)
        num_customers = len(final_customer_ids)
        customer_word = "customer" if num_customers == 1 else "customers"

        nudge = CoPilotNudge(
            business_id=business_id,
            customer_id=None,
            nudge_type=NudgeTypeEnum.GOAL_OPPORTUNITY,
            status=NudgeStatusEnum.ACTIVE,
            message_snippet=f"{num_customers} previously high-value {customer_word} have been inactive for over 90 days.",
            ai_suggestion="Launch a re-engagement campaign to win them back.",
            ai_suggestion_payload={
                "opportunity_type": "RE_ENGAGEMENT_CAMPAIGN",
                "customer_ids": final_customer_ids,
                "draft_message": f"Hi {{customer_name}}, it's been a while! We're reaching out to our valued customers with a special offer: [YOUR_OFFER]. Let us know if you're interested! - {business.representative_name or business.business_name}"
            }
        )

        self.db.add(nudge)
        self.db.commit()
        self.db.refresh(nudge)
        
        logger.info(f"{log_prefix} Successfully created Re-engagement Campaign Nudge ID {nudge.id} for {num_customers} customers.")
        return [nudge]

