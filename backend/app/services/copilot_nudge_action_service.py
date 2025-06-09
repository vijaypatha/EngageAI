# backend/app/services/copilot_nudge_action_service.py
import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models import (
    CoPilotNudge,
    Customer,
    BusinessProfile,
    NudgeStatusEnum,
    NudgeTypeEnum
)
# We'll need TwilioService to send SMS
from app.services.twilio_service import TwilioService
from app.config import settings # For potential future use, like a base URL for review links
from datetime import datetime, timezone # Import datetime & timezone


logger = logging.getLogger(__name__)

class CoPilotNudgeActionService:
    def __init__(self, db: Session):
        self.db = db
        self.twilio_service = TwilioService(db) # Initialize TwilioService

    async def handle_request_review_action(self, nudge_id: int, business_id: int) -> CoPilotNudge:
        """
        Handles the 'REQUEST_REVIEW' action for a positive sentiment CoPilotNudge.
        Sends an SMS to the customer asking for a review and updates the nudge status.
        """
        logger.info(f"Handling 'REQUEST_REVIEW' action for CoPilotNudge ID: {nudge_id}, Business ID: {business_id}")

        nudge = self.db.query(CoPilotNudge).filter(
            CoPilotNudge.id == nudge_id,
            CoPilotNudge.business_id == business_id
        ).first()

        if not nudge:
            logger.error(f"CoPilotNudge ID {nudge_id} not found for business {business_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nudge not found.")

        if nudge.nudge_type != NudgeTypeEnum.SENTIMENT_POSITIVE:
            logger.warning(f"CoPilotNudge ID {nudge_id} is not a positive sentiment nudge. Type: {nudge.nudge_type}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This action is only valid for positive sentiment nudges.")

        if nudge.status == NudgeStatusEnum.ACTIONED:
            logger.info(f"CoPilotNudge ID {nudge_id} has already been actioned. No further action taken.")
            return nudge
        
        if nudge.status == NudgeStatusEnum.DISMISSED:
            logger.info(f"CoPilotNudge ID {nudge_id} was dismissed. No action taken.")
            # Or, you might allow actioning a dismissed nudge, depending on product requirements
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nudge was dismissed and cannot be actioned.")


        if not nudge.customer_id:
            logger.error(f"CoPilotNudge ID {nudge_id} does not have an associated customer_id.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nudge is not associated with a specific customer.")

        customer = self.db.query(Customer).filter(Customer.id == nudge.customer_id).first()
        if not customer:
            logger.error(f"Customer ID {nudge.customer_id} associated with CoPilotNudge {nudge_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated customer not found.")

        business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
        if not business: # Should not happen if nudge exists with business_id
            logger.error(f"Business profile ID {business_id} not found.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Business profile configuration error.")

        if not customer.opted_in:
            logger.warning(f"Customer {customer.id} ({customer.phone}) has not opted in. Cannot send review request for nudge {nudge.id}.")
            # Update nudge status to error or keep as active with a note?
            # For now, let's prevent sending and not change nudge status, letting user know.
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customer has not opted in to receive messages.")

        # Compose the review request SMS
        review_link = business.review_platform_url
        customer_first_name = customer.customer_name.split(' ')[0] if customer.customer_name else 'there'
        
        if review_link:
            message_body = (
                f"Hi {customer_first_name}, we're so glad you had a great experience with {business.business_name}! "
                f"If you have a moment, we'd love for you to share your feedback. You can leave us a review here: {review_link}\n\n"
                f"Thank you!"
            )
        else:
            # Fallback message if review_platform_url is not set
            logger.warning(f"Business ID {business_id} does not have a review_platform_url set. Sending generic thank you for nudge {nudge.id}.")
            message_body = (
                f"Hi {customer_first_name}, we're so glad you had a great experience with {business.business_name}! "
                f"Your feedback is important to us. Thank you for choosing us!"
            )
            # Note: Without a link, this isn't a review request. Consider if this SMS should even be sent,
            # or if the action should be disallowed/warn user if no link is configured.
            # For now, it sends a thank you. Alternatively, you could raise an HTTPException:
            # raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Business review link is not configured. Cannot send review request.")

        # Signature is typically handled by TwilioService or part of the business style,
        # or you can append it here if needed: e.g., message_body += f"\n- {business.representative_name or business.business_name}"

        try:
            logger.info(f"Sending review request SMS to customer {customer.id} ({customer.phone}) for nudge {nudge.id}")
            # The send_sms method in TwilioService should handle using the business's Twilio number
            await self.twilio_service.send_sms(
                to=customer.phone,
                message_body=message_body,
                business=business, # Pass the full business object
                customer=customer,  # Pass customer for consent checks within twilio_service
                is_direct_reply=False # This is a proactive message triggered by an action
            )
            logger.info(f"Successfully sent review request SMS for nudge {nudge.id}.")

            # Update CoPilotNudge status
            nudge.status = NudgeStatusEnum.ACTIONED
            nudge.updated_at = datetime.now(timezone.utc)
            self.db.add(nudge)
            self.db.commit()
            self.db.refresh(nudge)
            logger.info(f"CoPilotNudge ID {nudge.id} status updated to ACTIONED.")
            return nudge

        except HTTPException as http_exc: # Re-raise HTTPExceptions from twilio_service
            logger.error(f"HTTPException while sending review request for nudge {nudge.id}: {http_exc.detail}")
            # Should we change nudge status here? Maybe to an error state or leave as active for retry?
            # For now, re-raising means the nudge status won't change in this attempt.
            raise http_exc
        except Exception as e:
            logger.error(f"Failed to send review request SMS for nudge {nudge_id}: {e}", exc_info=True)
            # Optionally, update nudge status to an error state here
            # nudge.status = NudgeStatusEnum.ERROR 
            # self.db.commit()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to send review request SMS: {str(e)}")