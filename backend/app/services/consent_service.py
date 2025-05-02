# Manages customer consent for SMS communications, allowing businesses to track who has opted in/out of receiving messages
# Business owners can see which customers have given permission to receive messages and manage their communication preferences
from fastapi import HTTPException, status, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from app.models import Customer, ConsentLog, BusinessProfile
from app.schemas import ConsentCreate
from app.services.twilio_service import TwilioService
from app.database import get_db
from typing import Optional
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class ConsentService:
    def __init__(self, db: Session):
        self.db = db
        self.twilio_service = TwilioService(db)

    async def send_double_optin_sms(self, customer_id: int, business_id: int) -> dict:
        """
        Send a double opt-in SMS to a customer requesting consent for SMS communications.
        """
        try:
            # Get customer and business info
            customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
            if not customer:
                logger.error(f"Customer {customer_id} not found")
                return {"success": False, "message": "Customer not found"}

            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
            if not business:
                logger.error(f"Business {business_id} not found")
                return {"success": False, "message": "Business not found"}

            # Prepare opt-in message
            message = (
                f"Hi {customer.customer_name}, {business.business_name} would like to send you SMS updates. "
                "Reply YES to opt in or NO to decline. Msg&data rates may apply."
            )

            # Send SMS via Twilio
            sid = await self.twilio_service.send_sms(
                to=customer.phone,
                message=message,
                business=business
            )

            if not sid:
                logger.error(f"Failed to send opt-in SMS to customer {customer_id}")
                return {"success": False, "message": "Failed to send opt-in SMS"}

            # Log the consent request
            consent_log = ConsentLog(
                customer_id=customer_id,
                business_id=business_id,
                method="sms",
                phone_number=customer.phone,
                message_sid=sid,
                status="pending",
                sent_at=datetime.now(timezone.utc)
            )
            self.db.add(consent_log)
            self.db.commit()

            return {
                "success": True,
                "message": "Opt-in SMS sent successfully",
                "message_sid": sid
            }

        except Exception as e:
            logger.error(f"Error sending double opt-in SMS: {str(e)}")
            return {
                "success": False,
                "message": f"Error sending opt-in SMS: {str(e)}"
            }

    async def process_sms_response(self, phone_number: str, response: str) -> Optional[PlainTextResponse]:
        """
        Process an SMS response for opt-in/out. Returns a PlainTextResponse if the message
        matches consent logic, else None.
        """
        try:
            # Find the most recent consent log for this phone number
            consent_log = self.db.query(ConsentLog).filter(
                ConsentLog.phone_number == phone_number,
                ConsentLog.status == "pending"
            ).order_by(ConsentLog.sent_at.desc()).first()

            if not consent_log:
                logger.warning(f"No pending consent log found for {phone_number}")
                return None

            # Get the customer and business
            customer = self.db.query(Customer).filter(Customer.id == consent_log.customer_id).first()
            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == consent_log.business_id).first()
            
            if not customer or not business:
                logger.error("Customer or business not found for consent log")
                return None

            # Process the response
            normalized = response.strip("!., ").lower()
            
            if normalized in ["yes", "yes!"]:
                customer.opted_in = True
                customer.opted_in_at = datetime.now(timezone.utc)
                consent_log.status = "opted_in"
                consent_log.replied_at = datetime.now(timezone.utc)
                self.db.commit()
                return PlainTextResponse("Opt-in confirmed. To opt out, reply STOP.", status_code=200)

            elif normalized in ["stop", "unsubscribe", "no", "no!"]:
                customer.opted_in = False
                consent_log.status = "declined"
                consent_log.replied_at = datetime.now(timezone.utc)
                self.db.commit()
                return PlainTextResponse("Opt-out confirmed", status_code=200)

            return None

        except Exception as e:
            logger.error(f"Error processing SMS response: {str(e)}")
            return None

    async def check_consent(self, phone_number: str, business_id: int) -> bool:
        """Check if a customer has opted in"""
        try:
            customer = self.db.query(Customer).filter(
                Customer.phone == phone_number,
                Customer.business_id == business_id
            ).first()
            
            if not customer:
                return False
                
            return customer.opted_in
            
        except Exception as e:
            logger.error(f"Error checking consent: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to check consent status"
            )

    async def get_consent_history(self, customer_id: int, business_id: int) -> list:
        """Get consent history for a customer"""
        try:
            logs = self.db.query(ConsentLog).filter(
                ConsentLog.customer_id == customer_id,
                ConsentLog.business_id == business_id
            ).order_by(ConsentLog.sent_at.desc()).all()
            
            return [{
                "id": log.id,
                "status": log.status,
                "method": log.method,
                "sent_at": log.sent_at,
                "replied_at": log.replied_at,
                "message_sid": log.message_sid
            } for log in logs]
            
        except Exception as e:
            logger.error(f"Error getting consent history: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get consent history"
            ) 
        
    async def handle_opt_in(self, phone_number: str, business_id: int, customer_id: int):
        """Create a ConsentLog entry for an opt-in"""
        try:
            consent_log = ConsentLog(
                phone_number=phone_number,
                business_id=business_id,
                customer_id=customer_id,
                status="opted_in",
                method="double_optin_sms",
                replied_at=datetime.now(timezone.utc)
            )
            self.db.add(consent_log)
            self.db.commit()
            self.db.refresh(consent_log)
            return consent_log
        except Exception as e:
            logger.error(f"Error handling opt-in manually: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record opt-in"
            )

    async def handle_opt_out(self, phone_number: str, business_id: int, customer_id: int):
        """Create a ConsentLog entry for an opt-out"""
        try:
            consent_log = ConsentLog(
                phone_number=phone_number,
                business_id=business_id,
                customer_id=customer_id,
                status="opted_out",
                method="double_optin_sms",
                replied_at=datetime.now(timezone.utc)
            )
            self.db.add(consent_log)
            self.db.commit()
            self.db.refresh(consent_log)
            return consent_log
        except Exception as e:
            logger.error(f"Error handling opt-out manually: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record opt-out"
            )

    async def send_opt_in_sms(self, phone_number: str, business_id: int, customer_id: int):
        """
        Sends a personalized opt-in SMS to the customer.
        """
        from app.models import BusinessProfile
        business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
        if not business:
            raise Exception("Business not found")

        # Use representative_name if available, otherwise fallback to business_name
        rep_name = business.representative_name or business.business_name

        message = (
            f"To start receiving messages from {business.business_name}, reply YES to opt in.\n"
            "We respect your privacy and will never send spam—only helpful updates and offers.\n"
            f"- {rep_name}\n"
            "Reply STOP at any time to unsubscribe."
        )

        await self.twilio_service.send_sms(
            to=phone_number,
            message=message,
            business=business
        )