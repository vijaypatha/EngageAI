# backend/app/services/twilio_service.py

# Manages all Twilio-related operations including SMS sending, phone number management, and OTP delivery
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional

from fastapi import status
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import Session
from twilio.rest import Client

from app.config import settings
from app.database import SessionLocal # Keep SessionLocal if it's used by send_sms_via_twilio
from app.models import BusinessProfile, Customer, Message

# Configure logging
logger = logging.getLogger(__name__)

class TwilioService:
    """Service for managing Twilio communications and phone number operations."""

    def __init__(self, db: Session):
        """
        Initialize TwilioService with database session.

        Args:
            db: Database session
        """
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.db = db

    # ------------------------------
    # Phone Number Management Methods
    # ------------------------------

    async def get_available_numbers(
        self,
        country_code: str = "US",
        area_code: Optional[str] = None,
        postal_code: Optional[str] = None
    ):
        logger.info(f"Starting get_available_numbers with country_code={country_code}, area_code={area_code}, postal_code={postal_code}")
        search_params = {"limit": 10}
        if area_code:
            search_params["area_code"] = area_code
            logger.info(f"TwilioService searching with area_code: {area_code}")
        elif postal_code:
            search_params["in_postal_code"] = postal_code
            logger.info(f"TwilioService searching with postal_code: {postal_code}")
        else:
            logger.info(f"TwilioService searching without area_code or postal_code filter (country={country_code}).")

        try:
            numbers = self.client.available_phone_numbers(country_code).local.list(**search_params)
            logger.debug(f"Twilio get_available_numbers response count: {len(numbers)}")
            results = [{
                "phone_number": number.phone_number,
                "friendly_name": number.friendly_name,
                "locality": number.locality,
                "region": number.region
            } for number in numbers]
            logger.info(f"get_available_numbers completed successfully with {len(results)} numbers found")
            return results
        except Exception as e:
            logger.error(f"get_available_numbers failed with params {search_params}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not retrieve numbers from provider: {str(e)}"
            )

    async def purchase_number(self, phone_number: str):
        logger.info(f"Starting purchase_number for phone_number={phone_number}")
        try:
            number = self.client.incoming_phone_numbers.create(phone_number=phone_number)
            logger.debug(f"Twilio purchase_number response: sid={number.sid}, phone_number={number.phone_number}")
            logger.info(f"Successfully purchased number {phone_number}")
            return {
                "status": "success",
                "message": f"Successfully purchased number {phone_number}",
                "phone_number": number.phone_number,
                "sid": number.sid
            }
        except Exception as e:
            logger.error(f"purchase_number failed for phone_number={phone_number}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, # Or 503 if Twilio issue
                detail=f"Failed to purchase number: {str(e)}"
            )

    async def purchase_and_assign_number_to_business(self, business_id: int, phone_number: str):
        logger.info(f"Starting purchase_and_assign_number_to_business for business_id={business_id}, phone_number={phone_number}")
        try:
            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
            if not business:
                logger.warning(f"purchase_and_assign_number_to_business failed: Business not found with id={business_id}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

            purchase_result = await self.purchase_number(phone_number)
            if not purchase_result or purchase_result.get('status') != 'success':
                logger.warning(f"purchase_and_assign_number_to_business failed: Failed to purchase number {phone_number}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to purchase number from provider")

            messaging_service_sid = settings.TWILIO_DEFAULT_MESSAGING_SERVICE_SID
            if not messaging_service_sid:
                logger.error("purchase_and_assign_number_to_business: TWILIO_DEFAULT_MESSAGING_SERVICE_SID is not set in settings.")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Default messaging service not configured.")
            
            try:
                self.client.messaging.services(messaging_service_sid).phone_numbers.create(
                    phone_number_sid=purchase_result.get('sid')
                )
                logger.info(f"📦 Attached phone number {phone_number} (SID: {purchase_result.get('sid')}) to Messaging Service {messaging_service_sid}")
            except Exception as attach_error:
                logger.error(f"❌ Failed to attach phone number {phone_number} to Messaging Service {messaging_service_sid}: {str(attach_error)}", exc_info=True)
                # Consider if releasing the purchased number is appropriate here if attachment fails.
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to attach number to messaging service.")

            business.twilio_number = phone_number
            business.twilio_sid = purchase_result.get('sid')
            business.messaging_service_sid = messaging_service_sid
            self.db.commit()

            logger.info(f"Twilio number {phone_number} purchased and assigned to business {business.business_name} (id={business_id})")
            return {
                "status": "success",
                "message": f"Twilio number {phone_number} purchased and assigned to business {business.business_name}",
                "business_id": business_id,
                "twilio_number": phone_number,
                "twilio_sid": purchase_result.get('sid')
            }
        except HTTPException as http_exc:
            raise http_exc
        except Exception as e:
            logger.error(f"purchase_and_assign_number_to_business failed for business_id={business_id}, phone_number={phone_number}: {str(e)}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal error assigning number: {str(e)}")

    async def release_twilio_number_by_phone(self, phone_number: str):
        logger.info(f"Starting release_twilio_number_by_phone for phone_number={phone_number}")
        try:
            numbers = self.client.incoming_phone_numbers.list(phone_number=phone_number)
            if not numbers:
                logger.warning(f"release_twilio_number_by_phone: Twilio number {phone_number} not found in account")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Twilio number {phone_number} not found in account")
            numbers[0].delete()
            logger.info(f"Released Twilio number {phone_number} successfully")
            return {"status": "success", "message": f"Released Twilio number {phone_number}"}
        except Exception as e:
            logger.error(f"release_twilio_number_by_phone failed for phone_number={phone_number}: {str(e)}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Failed to release number from provider: {str(e)}")

    async def release_assigned_twilio_number(self, business_id: int):
        logger.info(f"Starting release_assigned_twilio_number for business_id={business_id}")
        business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
        if not business or not business.twilio_sid:
            logger.warning(f"release_assigned_twilio_number failed: No assigned Twilio number to release for business_id={business_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No assigned Twilio number to release for this business.")

        try:
            self.client.incoming_phone_numbers(business.twilio_sid).delete()
            logger.info(f"✅ Released Twilio number with SID: {business.twilio_sid} for business_id={business_id}")
        except Exception as e:
            logger.error(f"❌ Failed to release Twilio number (SID: {business.twilio_sid}) for business_id={business_id}: {str(e)}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Failed to release Twilio number from provider: {str(e)}")

        business.twilio_number = None
        business.twilio_sid = None
        # business.messaging_service_sid = None # Decide if MSID should also be cleared
        self.db.commit()
        logger.info(f"🧹 Cleared assigned Twilio number for business ID {business_id}")
        return {"status": "success", "message": "Assigned Twilio number released and cleared from business profile"}

    # ------------------------------
    # SMS Sending Methods
    # ------------------------------

    async def send_sms(self, to: str, message: str, business: BusinessProfile) -> str:
        """
        Sends an SMS message via Twilio.
        Uses the business's specific twilio_number as the 'From' number if available,
        and always associates it with the business's messaging_service_sid for A2P compliance.

        Args:
            to: Recipient phone number
            message: SMS content to send
            business: BusinessProfile instance for the sender

        Returns:
            Twilio message SID
        """
        logger.info(f"Initiating send_sms to={to} for business_id={business.id if business else 'unknown'}.")
        logger.info(f"  Using business.twilio_number='{business.twilio_number}', business.messaging_service_sid='{business.messaging_service_sid}'")

        try:
            if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN]):
                logger.error(f"❌ send_sms aborted: Missing Twilio account credentials (TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN).")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="SMS provider account is not configured."
                )

            if not business.messaging_service_sid:
                logger.error(f"❌ send_sms aborted for business_id={business.id}: Missing messaging_service_sid. This is required for A2P compliance.")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Business messaging service identifier is not configured."
                )
            
            message_params = {
                "to": to,
                "messaging_service_sid": business.messaging_service_sid,
                "body": message
            }

            # <<< THIS IS THE KEY CHANGE: Add 'from_' if business.twilio_number is set >>>
            if business.twilio_number:
                message_params["from_"] = business.twilio_number
                logger.info(f"  Specific 'From' number '{business.twilio_number}' will be used.")
            else:
                # This case means the business relies on the Messaging Service to pick a number.
                # This could lead to the original issue if multiple numbers are in the service.
                # For your use case, business.twilio_number should ideally always be set.
                logger.warning(f"  No specific business.twilio_number set for business_id={business.id}. Messaging Service will select sender.")


            logger.info(f"📤 Attempting to send SMS with Twilio params: To='{message_params.get('to')}', From='{message_params.get('from_')}', MSID='{message_params.get('messaging_service_sid')}', Body='{message_params.get('body')[:30]}...'")
            
            twilio_msg = self.client.messages.create(**message_params)
            
            # Log details from Twilio's response
            logger.info(f"✅ SMS submission to Twilio successful. SID: {twilio_msg.sid}, Status: {twilio_msg.status}, From: {twilio_msg.from_}, To: {twilio_msg.to}, Price: {twilio_msg.price}")

            if twilio_msg.status in ['failed', 'undelivered']:
                error_detail = f"SMS provider reported error: {twilio_msg.error_message or 'Unknown reason'} (Code: {twilio_msg.error_code or 'N/A'})"
                logger.error(f"❌ Twilio send failed. SID: {twilio_msg.sid}, Status: {twilio_msg.status}, ErrorCode: {twilio_msg.error_code}, ErrorMsg: {twilio_msg.error_message}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=error_detail
                )
            
            return twilio_msg.sid

        except HTTPException as http_exc: # Re-raise known HTTPExceptions
            logger.error(f"❌ send_sms HTTP error for business_id={business.id if business else 'unknown'} to {to}: {http_exc.detail}", exc_info=True)
            raise http_exc
        except Exception as e:
            logger.error(f"❌ send_sms unexpected error for business_id={business.id if business else 'unknown'} to {to}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send SMS due to an internal server error: {str(e)}"
            )

    async def send_scheduled_message(self, message_id: int):
        logger.info(f"Starting send_scheduled_message for message_id={message_id}")
        try:
            message = self.db.query(Message).filter(
                Message.id == message_id,
                Message.message_type == 'scheduled' # Ensure it's a type we intend to send this way
            ).first()

            if not message:
                logger.warning(f"send_scheduled_message: Message ID {message_id} not found or not of type 'scheduled'.")
                return False # Or raise error, depending on desired strictness

            customer = self.db.query(Customer).filter(Customer.id == message.customer_id).first()
            if not customer or not customer.phone:
                logger.warning(f"send_scheduled_message: Customer or customer phone not found for Message ID {message_id} (Customer ID {message.customer_id}).")
                # Optionally update message status to failed here
                return False

            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == message.business_id).first()
            if not business:
                logger.warning(f"send_scheduled_message: Business not found for Message ID {message_id} (Business ID {message.business_id}).")
                # Optionally update message status to failed here
                return False

            now_utc = datetime.now(timezone.utc)
            # Ensure scheduled_time is timezone-aware if comparing with now_utc
            scheduled_time_aware = message.scheduled_time
            if scheduled_time_aware and scheduled_time_aware.tzinfo is None: # If naive, assume UTC (adjust if it's local)
                scheduled_time_aware = scheduled_time_aware.replace(tzinfo=timezone.utc)

            if scheduled_time_aware and scheduled_time_aware > now_utc:
                logger.info(f"⏱️ Not time yet to send Message ID {message_id} (Scheduled: {scheduled_time_aware}, Now: {now_utc}).")
                return False # Not an error, just not time yet. Celery ETA handles this.

            # Crucial: Re-check opt-in status right before sending
            if not customer.opted_in:
                logger.warning(f"send_scheduled_message: Customer {customer.id} is opted out. Skipping send for Message ID {message_id}.")
                message.status = "failed" # Or a specific status like 'skipped_opt_out'
                message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': 'Customer opted out before send'}
                self.db.commit()
                return False


            logger.info(f"  Attempting to send Message ID {message_id} via self.send_sms...")
            sid = await self.send_sms(customer.phone, message.content, business)
            # self.send_sms will raise an exception if Twilio submission fails.

            # Update message status on successful submission via self.send_sms
            message.status = "sent"
            message.sent_at = datetime.now(timezone.utc) # Record send attempt time
            # sid is already logged by self.send_sms, but can add to metadata if desired
            message.message_metadata = {**(message.message_metadata or {}), 'twilio_message_sid': sid, 'last_send_attempt': message.sent_at.isoformat()}
            self.db.commit()

            logger.info(f"✅ Message ID {message_id} processed and marked as 'sent'. SID: {sid}")
            return True

        except HTTPException as http_exc: # Catch HTTP exceptions from self.send_sms
            logger.error(f"❌ send_scheduled_message HTTP error for message_id={message_id}: {http_exc.detail}", exc_info=True)
            # Mark message as failed if an HTTP error occurs during the send_sms call
            if message_id: # If we have a message_id
                msg_to_fail = self.db.query(Message).filter(Message.id == message_id).first()
                if msg_to_fail and msg_to_fail.status == "scheduled": # Avoid overwriting other terminal states
                    msg_to_fail.status = "failed"
                    msg_to_fail.message_metadata = {**(msg_to_fail.message_metadata or {}), 'failure_reason': f"Send error: {http_exc.detail}"}
                    self.db.commit()
            return False # Indicate failure
        except Exception as e:
            logger.error(f"❌ send_scheduled_message unexpected error processing message_id={message_id}: {str(e)}", exc_info=True)
            if message_id: # If we have a message_id
                msg_to_fail = self.db.query(Message).filter(Message.id == message_id).first()
                if msg_to_fail and msg_to_fail.status == "scheduled":
                    msg_to_fail.status = "failed"
                    msg_to_fail.message_metadata = {**(msg_to_fail.message_metadata or {}), 'failure_reason': f"Unexpected processing error: {str(e)}"}
                    self.db.commit()
            return False # Indicate failure

    # ------------------------------
    # OTP Sending Method
    # ------------------------------

    async def send_otp(self, phone_number: str, otp: str) -> str:
        logger.info(f"Starting send_otp to phone_number={phone_number}")
        try:
            if not all([
                settings.TWILIO_ACCOUNT_SID, 
                settings.TWILIO_AUTH_TOKEN, 
                settings.TWILIO_SUPPORT_MESSAGING_SERVICE_SID # Crucial for OTP
            ]):
                logger.error(f"❌ send_otp failed: Missing Twilio credentials or support messaging service SID.")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="OTP provider is not configured."
                )

            twilio_msg = self.client.messages.create(
                body=f"Your AI Nudge login code is: {otp}. Expires in 5 minutes.",
                messaging_service_sid=settings.TWILIO_SUPPORT_MESSAGING_SERVICE_SID,
                to=phone_number
            )
            logger.info(f"📤 Sent OTP to {phone_number}. SID: {twilio_msg.sid}, Status: {twilio_msg.status}")

            if twilio_msg.status in ['failed', 'undelivered']:
                error_detail = f"OTP provider reported error: {twilio_msg.error_message or 'Unknown reason'} (Code: {twilio_msg.error_code or 'N/A'})"
                logger.error(f"❌ Twilio OTP send failed. SID: {twilio_msg.sid}, Status: {twilio_msg.status}, Error: {error_detail}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=error_detail
                )
            return twilio_msg.sid
        except HTTPException as http_exc:
            raise http_exc
        except Exception as e:
            logger.error(f"❌ send_otp failed to send to {phone_number}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send OTP due to an internal error: {str(e)}"
            )


async def send_sms_via_twilio(to: str, message: str, business: BusinessProfile) -> str:
    """
    Standalone function to send SMS via Twilio for backward compatibility or direct calls.
    Uses TwilioService internally.
    """
    db = None # Initialize db to None for finally block
    try:
        db = SessionLocal()
        service = TwilioService(db) # Pass the new session to the service
        return await service.send_sms(to, message, business)
    # No need to catch exceptions here if service.send_sms handles them and raises HTTPExceptions
    finally:
        if db:
            db.close()