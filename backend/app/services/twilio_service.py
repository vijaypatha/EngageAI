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
from app.models import BusinessProfile as BusinessProfileModel, Customer as CustomerModel, ConsentLog as ConsentLogModel, OptInStatus # Make sure OptInStatus is imported from models
from app.schemas import normalize_phone_number # Ensure this is imported from schemas
from app.config import settings # Ensure settings is imported
from sqlalchemy import desc 



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
        message_body: str,
        business: BusinessProfileModel,
        customer: Optional[CustomerModel] = None,
        is_direct_reply: bool = False,
        is_owner_notification: bool = False # ADDED THIS NEW PARAMETER
    ) -> Optional[str]: # Return type is Optional[str] for the SID or None on failure
        db = self.db 
        log_prefix = f"[TwilioService.send_sms BIZ:{business.id} TO:{to}]"

        if not to or not message_body:
            logger.error(f"{log_prefix} 'to' and 'message_body' are required.")
            # Consider raising an exception or returning a more specific error indicator
            # For now, returning None as per the function's signature.
            raise ValueError("'to' and 'message_body' are required for send_sms")


        try:
            normalized_to_phone = normalize_phone_number(to)
        except ValueError as e:
            logger.error(f"{log_prefix} Invalid 'to' phone number: {to}. Error: {e}")
            raise ValueError(f"Invalid 'to' phone number: {to}")


        # Determine which messaging service SID to use
        # If the business has its own Twilio number (meaning it went through onboarding step 5),
        # it should also have a messaging_service_sid set (which is the default one for now).
        # If it's an OTP or system message (like owner notification not tied to a specific business twilio_number),
        # it might use settings.TWILIO_SUPPORT_MESSAGING_SERVICE_SID.
        # For now, we assume 'business.messaging_service_sid' should be used if available.
        
        messaging_service_sid_to_use = business.messaging_service_sid
        from_number_to_use = business.twilio_number

        if is_owner_notification:
            # Owner notifications should ideally use a consistent, recognizable number/service if different
            # from the main business engagement MSID. For now, assume it uses the business's primary MSID or a global one.
            # If you have a specific SUPPORT_MESSAGING_SERVICE_SID for these, use it.
            if settings.TWILIO_SUPPORT_MESSAGING_SERVICE_SID: # Check if a dedicated support/notification MSID exists
                 messaging_service_sid_to_use = settings.TWILIO_SUPPORT_MESSAGING_SERVICE_SID
                 # For owner notifications sent via a general support MSID, 'from_' might be omitted (Twilio picks from pool)
                 # or you might have a specific 'from' number for support.
                 # If using the business's MSID for owner notifications, from_number_to_use remains business.twilio_number
                 logger.info(f"{log_prefix} Owner notification will use TWILIO_SUPPORT_MESSAGING_SERVICE_SID: {messaging_service_sid_to_use}")
            elif not messaging_service_sid_to_use: # Fallback if business has no MSID and no support MSID
                 logger.error(f"{log_prefix} No MessagingService SID available for owner notification (business or support).")
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Messaging service not configured for notifications.")
            # If from_number_to_use is None when using support MSID, Twilio will pick a number from that service's pool.
            # This is okay for OTPs/notifications.
            if messaging_service_sid_to_use == settings.TWILIO_SUPPORT_MESSAGING_SERVICE_SID:
                from_number_to_use = None # Let Twilio pick from the Support MSID pool

        elif not messaging_service_sid_to_use:
            logger.error(f"{log_prefix} No MessagingService SID configured for business {business.id}.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Business messaging service not configured.")
        
        if not is_owner_notification and not from_number_to_use : # Regular messages require a from number
            logger.error(f"{log_prefix} No 'From' number (business.twilio_number) configured for business {business.id} for regular SMS.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Business sender number not configured.")


        # Safely get text content for logging preview
        log_message_body_preview = message_body
        if isinstance(message_body, dict) and "text" in message_body: # Should not happen if webhook cleans it
            log_message_body_preview = message_body["text"]
        elif not isinstance(message_body, str):
            log_message_body_preview = str(message_body)
        
        logger.info(
            f"{log_prefix} Final check before Twilio. To: {normalized_to_phone}, "
            f"From: {from_number_to_use if from_number_to_use else 'MSID Pool'}, MSID: {messaging_service_sid_to_use}, "
            f"OwnerNotify: {is_owner_notification}, DirectReply: {is_direct_reply}. "
            f"Body: '{log_message_body_preview[:100]}...'"
        )

        # --- MODIFIED CONSENT CHECK ---
        if not is_owner_notification: # Skip consent checks for owner notifications
            target_customer_for_consent_check = customer
            if not target_customer_for_consent_check and not is_direct_reply:
                target_customer_for_consent_check = db.query(CustomerModel).filter(
                    CustomerModel.phone == normalized_to_phone,
                    CustomerModel.business_id == business.id
                ).first()

            if target_customer_for_consent_check:
                # Using sms_opt_in_status from Customer model which should be authoritative
                customer_consent_status = target_customer_for_consent_check.sms_opt_in_status

                if customer_consent_status == OptInStatus.OPTED_OUT.value:
                    logger.warning(
                        f"{log_prefix} Attempted to send SMS to OPTED_OUT customer "
                        f"{target_customer_for_consent_check.id}. Message blocked."
                    )
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot send message: Customer has opted out.")

                if not is_direct_reply and customer_consent_status != OptInStatus.OPTED_IN.value:
                    logger.warning(
                        f"{log_prefix} Attempted to send PROACTIVE SMS to customer "
                        f"{target_customer_for_consent_check.id} with status '{customer_consent_status}'. Message blocked."
                    )
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot send message: Customer has not opted in for proactive messages.")
            
            elif not is_direct_reply: # Proactive message to a number not in this business's customer list
                logger.warning(
                    f"{log_prefix} Attempted to send PROACTIVE SMS to an unknown/non-customer number "
                    f"'{normalized_to_phone}' for business {business.id}. Message blocked."
                )
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot send proactive message: Recipient is not an opted-in customer of this business.")
        # --- END OF MODIFIED CONSENT CHECK ---

        try:
            # Ensure actual_twilio_message_body is a string
            actual_twilio_message_body = message_body
            if not isinstance(message_body, str):
                 logger.warning(f"{log_prefix} message_body is not a string (type: {type(message_body)}). Attempting str().")
                 actual_twilio_message_body = str(message_body)

            create_params = {
                'to': normalized_to_phone,
                'messaging_service_sid': messaging_service_sid_to_use,
                'body': actual_twilio_message_body
            }
            if from_number_to_use: # Only add 'from_' if it's specified (e.g., not for support MSID pool)
                create_params['from_'] = from_number_to_use
            
            twilio_msg = self.client.messages.create(**create_params)
            
            logger.info(f"{log_prefix} SMS sent via Twilio. SID: {twilio_msg.sid}, Status: {twilio_msg.status}")
            return twilio_msg.sid
        
        except TwilioRestException as e:
            logger.error(f"{log_prefix} Twilio API error: {e.status} - {e.msg}", exc_info=True)
            if e.code == 21610: # Opted-out recipient
                 raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Twilio error: Recipient {normalized_to_phone} has opted out or is blocked.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE if e.status >= 500 else status.HTTP_400_BAD_REQUEST,
                detail=f"SMS provider error: {e.msg}"
            )
        except HTTPException as http_exc: # Re-raise HTTPExceptions we've raised intentionally
            raise http_exc
        except Exception as e: # Catch any other unexpected error during the send
            logger.error(f"{log_prefix} Unexpected error sending SMS: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send SMS due to an unexpected internal error: {str(e)}"
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