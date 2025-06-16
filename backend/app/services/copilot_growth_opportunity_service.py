# backend/app/services/copilot_growth_opportunity_service.py
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, text
from datetime import datetime, timedelta
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
    Message,
    MessageTypeEnum,
    MessageStatusEnum,
)
from app.schemas import CoPilotNudgeCreate

logger = logging.getLogger(__name__)

class CoPilotGrowthOpportunityService:
    def __init__(self, db: Session):
        self.db = db

    def identify_referral_opportunities(self, business_id: int) -> List[CoPilotNudge]:
        log_prefix = f"[GrowthSvc-Referral B:{business_id}]"
        logger.info(f"{log_prefix} Starting referral opportunity analysis.")
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        sixty_days_ago = datetime.utcnow() - timedelta(days=60)

        happy_customers_query = self.db.query(CoPilotNudge.customer_id).filter(
            CoPilotNudge.business_id == business_id,
            CoPilotNudge.nudge_type == NudgeTypeEnum.SENTIMENT_POSITIVE,
            CoPilotNudge.created_at >= thirty_days_ago
        ).distinct()

        serviced_customers_query = self.db.query(TargetedEvent.customer_id).filter(
            TargetedEvent.business_id == business_id,
            TargetedEvent.status == 'Completed',
            TargetedEvent.event_datetime_utc >= sixty_days_ago
        ).distinct()
        
        happy_customer_ids = {row[0] for row in happy_customers_query.all()}
        serviced_customer_ids = {row[0] for row in serviced_customers_query.all()}
        target_customer_ids = list(happy_customer_ids.intersection(serviced_customer_ids))

        if not target_customer_ids:
            logger.info(f"{log_prefix} No customers met the criteria for a new referral campaign.")
            return []

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

        business = self.db.query(BusinessProfile).get(business_id)
        num_customers = len(final_customer_ids)
        customer_word = "customer" if num_customers == 1 else "customers"

        nudge = CoPilotNudge(
            business_id=business_id,
            customer_id=None,
            nudge_type=NudgeTypeEnum.GOAL_OPPORTUNITY,
            status=NudgeStatusEnum.ACTIVE,
            message_snippet=f"You have {num_customers} happy {customer_word} who recently completed their service.",
            ai_suggestion="Launch a referral campaign to this group to drive word-of-mouth growth.",
            ai_suggestion_payload={
                "opportunity_type": "REFERRAL_CAMPAIGN",
                "customer_ids": final_customer_ids,
                "reason_to_believe": f"This group of {num_customers} recently had a positive experience and completed a service, making them ideal candidates to ask for a referral.",
                "ai_suggestion": "Launch a referral campaign to this group to drive word-of-mouth growth.",
                "draft_message": f"Hi {{customer_name}}, we're so glad you had a great experience with us! As a thank you, we'd like to offer you [YOUR_OFFER] for any friend you refer. Thanks, {business.representative_name or business.business_name}"
            }
        )
        
        self.db.add(nudge)
        self.db.commit()
        self.db.refresh(nudge)
        
        logger.info(f"{log_prefix} Successfully created Referral Campaign Nudge ID {nudge.id} for {num_customers} customers.")
        return [nudge]
    
    async def launch_growth_campaign_from_nudge(self, nudge_id: int, business_id_from_auth: int) -> Dict[str, Any]:
        log_prefix = f"[GrowthSvc-CreateDraft B:{business_id_from_auth} N:{nudge_id}]"
        logger.info(f"{log_prefix} Received request to create draft campaign from nudge for Approval Queue.")

        nudge = self.db.query(CoPilotNudge).filter(
            CoPilotNudge.id == nudge_id, CoPilotNudge.business_id == business_id_from_auth
        ).first()

        if not nudge or nudge.status != NudgeStatusEnum.ACTIVE or nudge.nudge_type != NudgeTypeEnum.GOAL_OPPORTUNITY:
            raise HTTPException(status_code=404, detail="Active goal opportunity nudge not found.")

        payload = nudge.ai_suggestion_payload or {}
        customer_ids = payload.get("customer_ids", [])
        draft_template = payload.get("draft_message")

        if not customer_ids or not draft_template:
            raise HTTPException(status_code=400, detail="Nudge data is incomplete.")

        customers_to_message = self.db.query(Customer).filter(
            Customer.id.in_(customer_ids),
            Customer.business_id == business_id_from_auth
        ).all()
        
        if len(customers_to_message) != len(customer_ids):
             logger.warning(f"{log_prefix} Some customer IDs were not found or did not belong to the business.")

        drafts_created_count = 0
        
        for customer in customers_to_message:
            personalized_message = draft_template.replace('{customer_name}', customer.customer_name or 'there')
            
            new_draft = Message(
                business_id=business_id_from_auth,
                customer_id=customer.id,
                content=personalized_message,
                status=MessageStatusEnum.PENDING_APPROVAL,
                message_type=MessageTypeEnum.OUTBOUND,
                message_metadata={
                    "source": "copilot_growth_campaign",
                    "campaign_type": payload.get("opportunity_type"),
                    "reason_to_believe": payload.get("reason_to_believe"),
                    "ai_suggestion": payload.get("ai_suggestion"),
                    "nudge_id": nudge.id
                }
            )
            self.db.add(new_draft)
            drafts_created_count += 1
        
        nudge.status = NudgeStatusEnum.ACTIONED
        nudge.updated_at = datetime.utcnow()
        self.db.add(nudge)

        self.db.commit()
        logger.info(f"{log_prefix} Successfully created {drafts_created_count} message drafts for the Approval Queue.")

        return {"drafts_created": drafts_created_count, "message": f"{drafts_created_count} campaign drafts added to the Approval Queue."}

    def identify_re_engagement_opportunities(self, business_id: int) -> List[CoPilotNudge]:
        log_prefix = f"[GrowthSvc-ReEngage B:{business_id}]"
        logger.info(f"{log_prefix} Starting re-engagement opportunity analysis.")
        ninety_days_ago = datetime.utcnow() - timedelta(days=90)
        
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

        recent_message_customers_query = self.db.query(
            Message.customer_id
        ).filter(
            Message.business_id == business_id,
            Message.customer_id.in_(high_value_customer_ids),
            Message.created_at >= ninety_days_ago
        ).distinct()
        
        active_customer_ids = {row[0] for row in recent_message_customers_query.all()}
        inactive_customer_ids = list(high_value_customer_ids - active_customer_ids)

        if not inactive_customer_ids:
            logger.info(f"{log_prefix} No high-value customers have become inactive.")
            return []
            
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

        business = self.db.query(BusinessProfile).get(business_id)
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
                "reason_to_believe": f"This group of {num_customers} were high-value customers but haven't engaged in over 90 days. A special offer can help win them back.",
                "ai_suggestion": "Launch a re-engagement campaign to win them back.",
                "draft_message": f"Hi {{customer_name}}, it's been a while! We're reaching out to our valued customers with a special offer: [YOUR_OFFER]. Let us know if you're interested! - {business.representative_name or business.business_name}"
            }
        )

        self.db.add(nudge)
        self.db.commit()
        self.db.refresh(nudge)
        
        logger.info(f"{log_prefix} Successfully created Re-engagement Campaign Nudge ID {nudge.id} for {num_customers} customers.")
        return [nudge]
