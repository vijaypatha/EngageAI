# backend/app/services/twilio_service.py

# Manages all Twilio-related operations including SMS sending, phone number management, and OTP delivery
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional
import json # Import json to handle structured message bodies

from fastapi import status
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import Session
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


from app.config import settings
from app.database import SessionLocal
from app.models import BusinessProfile, Customer, Message, OptInStatus



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

    async def send_sms(
        self,
        to: str,
        message_body: str, # This parameter should ideally always be a string
        business: BusinessProfile,
        customer: Optional[Customer] = None,
        is_direct_reply: bool = False # Flag if this is a direct reply to a customer's message
    ) -> str:
        log_prefix = f"[TwilioService.send_sms BIZ:{business.id} TO:{to}]"

        # Safely get text content for logging preview
        log_message_content = message_body
        if isinstance(message_body, dict) and "text" in message_body:
            log_message_content = message_body["text"]
        elif not isinstance(message_body, str):
            # Fallback for logging if it's unexpectedly not string or dict with 'text'
            log_message_content = str(message_body)

        # Use the safe logging variable for the log preview line
        logger.info(f"{log_prefix} Attempting to send. Direct reply: {is_direct_reply}. Body: '{log_message_content[:50]}...'")


        if not customer:
            customer = self.db.query(Customer).filter(
                Customer.phone == to,
                Customer.business_id == business.id
            ).first()

        if not customer:
            logger.error(f"{log_prefix} Customer not found for phone {to} and business ID {business.id}. Cannot send.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not registered with this business.")

        # Consent check logic
        # Direct replies (is_direct_reply=True) are allowed even if customer is not fully opted-in.
        # Proactive messages (is_direct_reply=False) require OPTED_IN status.
        if customer.sms_opt_in_status == OptInStatus.OPTED_OUT:
            logger.warning(f"{log_prefix} Customer {customer.id} is OPTED_OUT. Message blocked. (Direct Reply: {is_direct_reply})")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot send message: Customer has opted out.")

        if not is_direct_reply and customer.sms_opt_in_status != OptInStatus.OPTED_IN:
             logger.warning(
                 f"{log_prefix} Attempted to send PROACTIVE SMS to customer {customer.id} "
                 f"with status '{customer.sms_opt_in_status}'. Message blocked."
             )
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot send message: Customer has not opted in for proactive messages.")


        try:
            if not self.client:
                logger.error(f"{log_prefix} Twilio client not initialized.")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SMS provider client not initialized.")

            if not business.messaging_service_sid:
                logger.error(f"{log_prefix} Missing messaging_service_sid for business_id={business.id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="SMS Messaging Service is not configured for this business."
                )

            if not business.twilio_number:
                logger.error(f"{log_prefix} Missing sender phone number (twilio_number) for business_id={business.id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Sender phone number not configured for this business."
                )

            # Defensive check: Ensure message_body is a string before sending to Twilio
            actual_twilio_message_body = message_body
            if isinstance(message_body, dict) and "text" in message_body:
                actual_twilio_message_body = message_body["text"]
            elif not isinstance(message_body, str):
                # If somehow not a string or expected dict structure, forcefully convert
                logger.warning(f"{log_prefix} message_body is not a string or expected dict (type: {type(message_body)}). Attempting str() conversion.")
                actual_twilio_message_body = str(message_body)


            logger.info(f"{log_prefix} Sending SMS from {business.twilio_number} via MSID {business.messaging_service_sid}.")
            twilio_msg = self.client.messages.create(
                to=to,
                messaging_service_sid=business.messaging_service_sid,
                from_=business.twilio_number, # Use the business's Twilio number as 'From'
                body=actual_twilio_message_body # Use the potentially converted string for Twilio
            )
            logger.info(f"{log_prefix} SMS sent successfully. SID: {twilio_msg.sid}")
            return twilio_msg.sid
        except HTTPException as http_exc:
            raise http_exc
        except TwilioRestException as e:
            logger.error(f"{log_prefix} Twilio API error: {e.status} - {e.msg}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE if e.status >= 500 else status.HTTP_400_BAD_REQUEST,
                detail=f"SMS provider error: {e.msg}"
            )
        except Exception as e:
            logger.error(f"{log_prefix} Unexpected error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send SMS due to an unexpected error: {str(e)}"
            )


    # In class TwilioService:
    async def send_scheduled_message(self, message_id: int):
        log_prefix = f"[TwilioService.send_scheduled_message MSG_ID:{message_id}]"
        logger.info(f"{log_prefix} Processing.")

        db_message_to_send = self.db.query(Message).filter(Message.id == message_id).first()

        if not db_message_to_send:
            logger.warning(f"{log_prefix} Message not found.")
            return False # Or raise error

        # Safely get content from message record (it might be JSON string from structured content)
        message_content = db_message_to_send.content
        if isinstance(message_content, str):
            try:
                # If it's a JSON string, try to parse and get the 'text'
                parsed_content = json.loads(message_content)
                if isinstance(parsed_content, dict) and "text" in parsed_content:
                    message_content = parsed_content["text"]
                # else, it's a string but not structured JSON, use as is
            except json.JSONDecodeError:
                # Not JSON, just use the plain string content
                pass # message_content is already the string

        if not isinstance(message_content, str):
             # If after parsing/checks it's still not a string, convert for sending
             logger.warning(f"{log_prefix} Message content from DB is not a string (type: {type(message_content)}). Attempting str() conversion.")
             message_content = str(message_content)

        if db_message_to_send.status not in ["scheduled", "pending_retry"]: # Check if it's eligible
            logger.info(f"{log_prefix} Message status is '{db_message_to_send.status}', not eligible for sending.")
            return False

        customer = self.db.query(Customer).filter(Customer.id == db_message_to_send.customer_id).first()
        if not customer or not customer.phone:
            logger.warning(f"{log_prefix} Customer or customer phone not found (CustID: {db_message_to_send.customer_id}).")
            db_message_to_send.status = "failed"
            db_message_to_send.message_metadata = {**(db_message_to_send.message_metadata or {}), 'failure_reason': 'Customer or phone not found'}
            self.db.commit()
            return False

        business = self.db.query(BusinessProfile).filter(BusinessProfile.id == db_message_to_send.business_id).first()
        if not business:
            logger.warning(f"{log_prefix} Business not found (BizID: {db_message_to_send.business_id}).")
            db_message_to_send.status = "failed"
            db_message_to_send.message_metadata = {**(db_message_to_send.message_metadata or {}), 'failure_reason': 'Business not found'}
            self.db.commit()
            return False

        # The self.send_sms method will now handle all opt-in checks.
        # Scheduled messages are proactive, so is_direct_reply=False.
        try:
            logger.info(f"{log_prefix} Calling self.send_sms to {customer.phone} for CustID {customer.id}.")
            sid = await self.send_sms(
                to=customer.phone,
                message_body=message_content, # Pass the extracted/converted string content
                business=business,
                customer=customer,
                is_direct_reply=False # Scheduled messages are proactive
            )

            db_message_to_send.status = "sent"
            db_message_to_send.sent_at = datetime.now(timezone.utc)
            db_message_to_send.message_metadata = {
                **(db_message_to_send.message_metadata or {}),
                'twilio_message_sid': sid,
                'last_send_attempt': db_message_to_send.sent_at.isoformat()
            }
            self.db.commit()
            logger.info(f"{log_prefix} Successfully processed and marked as 'sent'. SID: {sid}")
            return True

        except HTTPException as http_exc:
            logger.error(f"{log_prefix} Send error (HTTPException): {http_exc.detail}")
            # Update message status based on the HTTP Exception details if needed, e.g., opt-out/forbidden
            failure_reason = f"Send error: {http_exc.detail}"
            if http_exc.status_code == status.HTTP_403_FORBIDDEN:
                 failure_reason = "Customer opt-out or not opted-in for proactive messages."

            if db_message_to_send.status in ["scheduled", "pending_retry"]:
                db_message_to_send.status = "failed"
                db_message_to_send.message_metadata = {
                    **(db_message_to_send.message_metadata or {}),
                    'failure_reason': failure_reason,
                    'last_send_attempt': datetime.now(timezone.utc).isoformat()
                }
                self.db.commit()
            return False # Indicate failure

        except Exception as e:
            logger.error(f"{log_prefix} Unexpected error: {str(e)}", exc_info=True)
            if db_message_to_send.status in ["scheduled", "pending_retry"]:
                db_message_to_send.status = "failed"
                db_message_to_send.message_metadata = {
                    **(db_message_to_send.message_metadata or {}),
                    'failure_reason': f"Unexpected processing error: {str(e)}",
                    'last_send_attempt': datetime.now(timezone.utc).isoformat()
                }
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


# Standalone function for backward compatibility or direct calls.
# Uses TwilioService internally.
async def send_sms_via_twilio(to: str, message: str, business: BusinessProfile) -> str:
    """
    Standalone function to send SMS via Twilio for backward compatibility or direct calls.
    Uses TwilioService internally.
    """
    db = None # Initialize db to None for finally block
    try:
        db = SessionLocal()
        service = TwilioService(db) # Pass the new session to the service
        # Assuming standalone calls like this are NOT direct replies to customer inbound SMS
        return await service.send_sms(to=to, message_body=message, business=business, is_direct_reply=False)
    # No need to catch exceptions here if service.send_sms handles them and raises HTTPExceptions
    finally:
        if db:
            db.close()