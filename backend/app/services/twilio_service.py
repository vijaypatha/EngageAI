# Manages all Twilio-related operations including SMS sending, phone number management, and OTP delivery
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional

from fastapi import status
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import Session
from twilio.rest import Client

from app.config import settings
from app.database import SessionLocal
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
        self.client = Client(settings.TWILIO_SID, settings.TWILIO_AUTH_TOKEN)
        self.db = db

    # ------------------------------
    # Phone Number Management Methods
    # ------------------------------

    async def get_available_numbers(
        self,
        country_code: str = "US",
        area_code: Optional[str] = None,
        postal_code: Optional[str] = None  # Add postal_code parameter
    ):
        """
        Get available Twilio phone numbers, filtering by EITHER area code OR postal code.

        Args:
            country_code: Country code to search numbers in (default "US")
            area_code: Optional area code to filter numbers
            postal_code: Optional postal code to filter numbers (used if area_code not provided)

        Returns:
            List of available phone numbers with details
        """
        logger.info(f"Starting get_available_numbers with country_code={country_code}, area_code={area_code}, postal_code={postal_code}")
        # Build search parameters dictionary, prioritizing area_code if both provided
        search_params = {"limit": 10}  # Limit results
        if area_code:
            search_params["area_code"] = area_code
            logger.info(f"TwilioService searching with area_code: {area_code}")
        elif postal_code:
            search_params["in_postal_code"] = postal_code  # Use 'in_postal_code' for Twilio API
            logger.info(f"TwilioService searching with postal_code: {postal_code}")
        else:
            # Decide default behavior: search without filter or raise error?
            # Let's search without filter for now if route allows.
            logger.info(f"TwilioService searching without area_code or postal_code filter (country={country_code}).")

        try:
            numbers = self.client.available_phone_numbers(country_code).local.list(
                **search_params  # Pass parameters dynamically
            )
            logger.debug(f"Twilio get_available_numbers response count: {len(numbers)}")

            # Format the results
            results = [{
                "phone_number": number.phone_number,
                "friendly_name": number.friendly_name,
                "locality": number.locality,
                "region": number.region
            } for number in numbers]

            logger.info(f"get_available_numbers completed successfully with {len(results)} numbers found")
            return results

        except Exception as e:
            logger.error(f"get_available_numbers failed with params {search_params}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,  # Or 400 if params were bad
                detail=f"Could not retrieve numbers from provider: {str(e)}"
            )

    async def purchase_number(self, phone_number: str):
        """
        Purchase a specific Twilio phone number.

        Args:
            phone_number: Phone number string to purchase

        Returns:
            Dict with purchase status and details
        """
        logger.info(f"Starting purchase_number for phone_number={phone_number}")
        try:
            number = self.client.incoming_phone_numbers.create(
                phone_number=phone_number
            )
            logger.debug(f"Twilio purchase_number response: sid={number.sid}, phone_number={number.phone_number}")
            logger.info(f"Successfully purchased number {phone_number}")
            return {
                "status": "success",
                "message": f"Successfully purchased number {phone_number}",
                "phone_number": number.phone_number,
                "sid": number.sid
            }

        except Exception as e:
            logger.error(f"purchase_number failed for phone_number={phone_number}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    async def purchase_and_assign_number_to_business(self, business_id: int, phone_number: str):
        """
        Purchases a Twilio phone number and assigns it to a business.

        Args:
            business_id: ID of the business to assign the number to
            phone_number: Phone number string to purchase and assign

        Returns:
            Dict with assignment status and details
        """
        logger.info(f"Starting purchase_and_assign_number_to_business for business_id={business_id}, phone_number={phone_number}")
        try:
            business = self.db.query(BusinessProfile).filter(
                BusinessProfile.id == business_id
            ).first()

            if not business:
                logger.warning(f"purchase_and_assign_number_to_business failed: Business not found with id={business_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Business not found"
                )

            purchase_result = await self.purchase_number(phone_number)
            logger.debug(f"purchase_number result: {purchase_result}")
            if not purchase_result or purchase_result.get('status') != 'success':
                logger.warning(f"purchase_and_assign_number_to_business failed: Failed to purchase number {phone_number}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to purchase number from Twilio"
                )

            # Attach the purchased number to the default Messaging Service
            messaging_service_sid = settings.TWILIO_DEFAULT_MESSAGING_SERVICE_SID
            try:
                self.client.messaging.services(messaging_service_sid).phone_numbers.create(
                    phone_number_sid=purchase_result.get('sid')
                )
                logger.info(f"📦 Attached phone number {phone_number} (SID: {purchase_result.get('sid')}) to Messaging Service {messaging_service_sid}")
            except Exception as attach_error:
                logger.error(f"❌ Failed to attach phone number {phone_number} to Messaging Service {messaging_service_sid}: {str(attach_error)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to attach number to messaging service"
                )

            business.twilio_number = phone_number
            business.twilio_sid = purchase_result.get('sid')
            business.messaging_service_sid = messaging_service_sid  # Save MS SID to DB
            self.db.commit()

            logger.info(f"Twilio number {phone_number} purchased and assigned to business {business.business_name} (id={business_id})")
            return {
                "status": "success",
                "message": f"Twilio number {phone_number} purchased and assigned to business {business.business_name}",
                "business_id": business_id,
                "twilio_number": phone_number,
                "twilio_sid": purchase_result.get('sid')
            }

        except Exception as e:
            logger.error(f"purchase_and_assign_number_to_business failed for business_id={business_id}, phone_number={phone_number}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    async def release_twilio_number_by_phone(self, phone_number: str):
        """
        Releases a Twilio number from account using the phone number string.

        Args:
            phone_number: Phone number string to release

        Returns:
            Dict with release status and message
        """
        logger.info(f"Starting release_twilio_number_by_phone for phone_number={phone_number}")
        try:
            numbers = self.client.incoming_phone_numbers.list(
                phone_number=phone_number
            )

            if not numbers:
                logger.warning(f"release_twilio_number_by_phone: Twilio number {phone_number} not found in account")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Twilio number {phone_number} not found in account"
                )

            numbers[0].delete()
            logger.info(f"Released Twilio number {phone_number} successfully")
            return {
                "status": "success",
                "message": f"Released Twilio number {phone_number}"
            }

        except Exception as e:
            logger.error(f"release_twilio_number_by_phone failed for phone_number={phone_number}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    async def release_assigned_twilio_number(self, business_id: int):
        """
        Releases the assigned Twilio number for a business using its stored SID.

        Args:
            business_id: ID of the business whose Twilio number is to be released

        Returns:
            Dict with release status and message
        """
        logger.info(f"Starting release_assigned_twilio_number for business_id={business_id}")

        business = self.db.query(BusinessProfile).filter(
            BusinessProfile.id == business_id
        ).first()

        if not business or not business.twilio_sid:
            logger.warning(f"release_assigned_twilio_number failed: No assigned Twilio number to release for business_id={business_id}")
            raise HTTPException(status_code=404, detail="No assigned Twilio number to release")

        try:
            self.client.incoming_phone_numbers(business.twilio_sid).delete()
            logger.info(f"✅ Released Twilio number with SID: {business.twilio_sid} for business_id={business_id}")
        except Exception as e:
            logger.error(f"❌ Failed to release Twilio number (SID: {business.twilio_sid}) for business_id={business_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to release Twilio number: {str(e)}"
            )

        business.twilio_number = None
        business.twilio_sid = None
        self.db.commit()

        logger.info(f"🧹 Cleared assigned Twilio number for business ID {business_id}")
        return {
            "status": "success",
            "message": "Assigned Twilio number released and cleared from business profile"
        }

    # ------------------------------
    # SMS Sending Methods
    # ------------------------------

    async def send_sms(self, to: str, message: str, business: BusinessProfile) -> str:
        """
        Sends an SMS message via Twilio, using the business's messaging service SID.

        Args:
            to: Recipient phone number
            message: SMS content to send
            business: BusinessProfile instance for the sender

        Returns:
            Twilio message SID
        """
        logger.info(f"Starting send_sms to={to} for business_id={business.id if business else 'unknown'}")
        try:
            logger.info(f"🔍 business.messaging_service_sid = {business.messaging_service_sid}")
            if not all([
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN
            ]) or not business.messaging_service_sid:
                logger.error(f"❌ send_sms failed: Missing Twilio credentials or messaging service SID for business_id={business.id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="SMS provider is not configured"
                )

            twilio_msg = self.client.messages.create(
                to=to,
                messaging_service_sid=business.messaging_service_sid,
                body=message
            )
            logger.info(f"📤 Sent SMS to {to} via messaging service {business.messaging_service_sid}. SID: {twilio_msg.sid}")
            return twilio_msg.sid
        except Exception as e:
            logger.error(f"❌ send_sms failed to send to {to} for business_id={business.id if business else 'unknown'}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to send SMS: {str(e)}"
            )

    async def send_scheduled_message(self, message_id: int):
        """
        Processes and sends a scheduled message by its ID.

        Args:
            message_id: ID of the scheduled message to send

        Returns:
            True if message sent successfully, False otherwise
        """
        logger.info(f"Starting send_scheduled_message for message_id={message_id}")
        try:
            message = self.db.query(Message).filter(
                Message.id == message_id,
                Message.message_type == 'scheduled'
            ).first()

            if not message:
                logger.warning(f"send_scheduled_message: Message ID {message_id} not found")
                return False

            customer = self.db.query(Customer).filter(Customer.id == message.customer_id).first()
            if not customer or not customer.phone:
                logger.warning(f"send_scheduled_message: Customer not found or missing phone for Message ID {message_id}")
                return False

            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == message.business_id).first()
            if not business:
                logger.warning(f"send_scheduled_message: Business not found for Message ID {message_id}")
                return False

            # Check scheduled time
            now_utc = datetime.now(timezone.utc)
            if message.scheduled_time and message.scheduled_time > now_utc:
                logger.info(f"⏱️ Not time yet to send Message ID {message_id}")
                return False

            # Send the message
            sid = await self.send_sms(customer.phone, message.content, business)
            logger.debug(f"send_scheduled_message: SMS sent with SID {sid} for Message ID {message_id}")

            # Update message status
            message.status = "sent"
            message.sent_at = now_utc
            self.db.commit()

            logger.info(f"✅ Message ID {message_id} sent successfully")
            return True

        except Exception as e:
            logger.error(f"❌ send_scheduled_message error processing message_id={message_id}: {str(e)}")
            return False

    # ------------------------------
    # OTP Sending Method
    # ------------------------------

    async def send_otp(self, phone_number: str, otp: str) -> str:
        """
        Send OTP via SMS using Twilio's support messaging service (AI Nudge platform).

        Args:
            phone_number: Recipient's phone number
            otp: One-time password to send

        Returns:
            Twilio message SID

        Raises:
            HTTPException: If SMS sending fails
        """
        logger.info(f"Starting send_otp to phone_number={phone_number}")
        try:
            twilio_msg = self.client.messages.create(
                body=f"Your AI Nudge login code is: {otp}. Expires in 5 minutes.",
                messaging_service_sid=settings.TWILIO_SUPPORT_MESSAGING_SERVICE_SID,
                to=phone_number
            )
            logger.info(f"📤 Sent OTP to {phone_number}. SID: {twilio_msg.sid}")
            return twilio_msg.sid
        except Exception as e:
            logger.error(f"❌ send_otp failed to send to {phone_number}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send OTP: {str(e)}"
            )


async def send_sms_via_twilio(to: str, message: str, business: BusinessProfile) -> str:
    """
    Standalone function to send SMS via Twilio for backward compatibility.
    Uses TwilioService internally.

    Args:
        to: Recipient phone number
        message: SMS content to send
        business: BusinessProfile instance for the sender

    Returns:
        Twilio message SID

    Raises:
        HTTPException: If SMS sending fails
    """
    db = SessionLocal()
    try:
        service = TwilioService(db)
        return await service.send_sms(to, message, business)
    finally:
        db.close()