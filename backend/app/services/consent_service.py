# backend/app/services/consent_service.py
# Manages customer consent for SMS communications.

from fastapi import HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc # Ensure desc is imported
from app.models import Customer, ConsentLog, BusinessProfile # Ensure all are imported
# Schemas might not be directly needed in this service file unless used for internal validation
# from app.schemas import ConsentCreate
from app.services.twilio_service import TwilioService
from typing import Optional, List, Dict, Any # Ensure all are imported
import logging
from datetime import datetime, timezone # Ensure timezone is imported
from app import models

logger = logging.getLogger(__name__)

class ConsentService:
    def __init__(self, db: Session):
        self.db = db
        self.twilio_service = TwilioService(db=db)

    async def send_double_optin_sms(self, customer_id: int, business_id: int) -> Dict[str, Any]:
        """
        Send a double opt-in SMS to a customer requesting consent.
        """
        try:
            customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
            if not customer:
                logger.error(f"[ConsentService] Customer {customer_id} not found for double opt-in.")
                return {"success": False, "message": "Customer not found"}

            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
            if not business:
                logger.error(f"[ConsentService] Business {business_id} not found for double opt-in.")
                return {"success": False, "message": "Business not found"}

            rep_name = business.representative_name or business.business_name
            greeting_name = customer.customer_name or "there"

            message_content = (
                f"Hi {greeting_name}! This is {rep_name} from {business.business_name}. "
                f"We'd love to send you helpful updates & special offers via SMS. "
                f"To confirm, please reply YES. "
                f"Msg&Data rates may apply. Reply STOP at any time to unsubscribe."
            )

            sid = await self.twilio_service.send_sms(
                to=customer.phone,
                message_body=message_content,
                business=business,
                is_direct_reply=True
            )

            if not sid:
                logger.error(f"[ConsentService] Failed to send double opt-in SMS to customer {customer_id} (Twilio send failed).")
                return {"success": False, "message": "Failed to send opt-in SMS via provider."}

            consent_log = ConsentLog(
                customer_id=customer_id, business_id=business_id,
                method="sms_double_optin", phone_number=customer.phone, message_sid=sid,
                status="pending_confirmation", sent_at=datetime.now(timezone.utc)
            )
            self.db.add(consent_log)
            self.db.commit()
            logger.info(f"[ConsentService] Double opt-in SMS sent to customer {customer_id}. SID: {sid}")
            return {"success": True, "message": "Opt-in SMS sent successfully", "message_sid": sid }

        except ValueError as ve:
            logger.error(f"[ConsentService] Error in send_double_optin_sms setup: {ve}")
            return {"success": False, "message": str(ve)}
        except Exception as e:
            logger.error(f"[ConsentService] Unexpected error in send_double_optin_sms: {e}", exc_info=True)
            self.db.rollback() # Ensure rollback on unexpected error during DB ops
            return {"success": False, "message": "An unexpected error occurred."}


    async def process_sms_response(
        self,
        db_customer: models.Customer,        # The customer model instance
        business: models.BusinessProfile,    # The business model instance
        sms_body: str,                       # The content of the SMS from the customer
        message_sid: str,                    # The Twilio SID of the incoming message
        twilio_phone_number: str,            # The Twilio phone number that received the SMS
        business_phone: Optional[str] = None # The business's primary contact number (optional)
    ) -> Optional[PlainTextResponse]:
        """
        Process an SMS response from a customer for opt-in/out.
        - db_customer: The customer who sent the SMS.
        - business: The business profile associated with the Twilio number.
        - sms_body: The content of the customer's SMS.
        - message_sid: Twilio's SID for the incoming message.
        - twilio_phone_number: The Twilio number that received this SMS.
        - business_phone: The primary advertised phone number of the business (for context).
        """
        logger.info(
            f"[ConsentService] Processing SMS response. Customer ID: {db_customer.id} ({db_customer.phone}), "
            f"Business ID: {business.id} (Twilio#: {twilio_phone_number}, Primary Contact#: {business_phone}), "
            f"Message SID: {message_sid}, Body: '{sms_body}'"
        )
        try:
            # Fetch the most recent pending consent log for this customer and business.
            # A customer's consent is specific to a business.
            consent_log = self.db.query(ConsentLog).filter(
                ConsentLog.customer_id == db_customer.id,
                ConsentLog.business_id == business.id,
                ConsentLog.status.in_([models.OptInStatus.PENDING_CONFIRMATION.value, models.OptInStatus.PENDING.value])
            ).order_by(desc(ConsentLog.sent_at)).first()

            normalized_response = sms_body.strip("!.,? ").lower()
            current_time = datetime.now(timezone.utc)

            # Keywords
            opt_in_keywords = ["yes", "yes!", "yep", "yeah", "ok", "okay", "sounds good", "sure", "affirmative", "i agree", "agree", "confirm", "confirmed", "alright", "absolutely", "definitely", "subscribe", "opt in", "opt-in", "start"]
            decline_keywords = ["no", "no!", "nope", "nah", "decline", "i decline", "do not"]
            global_opt_out_keywords = ["stop", "stopall", "unsubscribe", "cancel", "end", "quit"]

            if consent_log:
                logger.info(f"[ConsentService] Found pending ConsentLog ID: {consent_log.id} for Customer {db_customer.id}.")
                if normalized_response in opt_in_keywords:
                    db_customer.sms_opt_in_status = models.OptInStatus.OPTED_IN
                    consent_log.status = models.OptInStatus.OPTED_IN.value
                    consent_log.replied_at = current_time
                    # self.db.commit() # Commit will be handled by the calling route or a final commit
                    logger.info(f"[ConsentService] Customer {db_customer.id} OPTED IN (pending log). Log ID: {consent_log.id}.")
                    return PlainTextResponse("Thanks for confirming! You're opted in. Reply STOP to unsubscribe.", status_code=status.HTTP_200_OK)
                elif normalized_response in decline_keywords:
                    db_customer.sms_opt_in_status = models.OptInStatus.DECLINED_BY_CUSTOMER # You might need to add this to your OptInStatus enum
                    consent_log.status = models.OptInStatus.DECLINED_BY_CUSTOMER.value # Or a more generic 'opted_out'
                    consent_log.replied_at = current_time
                    # self.db.commit()
                    logger.info(f"[ConsentService] Customer {db_customer.id} DECLINED consent (pending log). Log ID: {consent_log.id}.")
                    return PlainTextResponse("Okay, you won't receive these messages. Thanks.", status_code=status.HTTP_200_OK)
                elif normalized_response in global_opt_out_keywords:
                    db_customer.sms_opt_in_status = models.OptInStatus.OPTED_OUT
                    consent_log.status = models.OptInStatus.OPTED_OUT.value
                    consent_log.replied_at = current_time
                    # self.db.commit()
                    logger.info(f"[ConsentService] Customer {db_customer.id} OPTED OUT via global keyword (pending log). Log ID: {consent_log.id}.")
                    return PlainTextResponse("You have successfully been unsubscribed. You will not receive any more messages from this number. Reply START to resubscribe.", status_code=status.HTTP_200_OK)
                else:
                    logger.info(f"[ConsentService] SMS response '{sms_body}' from Customer {db_customer.id} did not match consent keywords for pending log {consent_log.id}.")
                    return None # Not a consent keyword for a PENDING log, let other services handle.
            else:
                # No PENDING consent log found. Check for global STOP/START for an existing customer.
                logger.info(f"[ConsentService] No pending consent log for Customer {db_customer.id}. Checking for global opt-out/opt-in.")
                if normalized_response in global_opt_out_keywords:
                    if db_customer.sms_opt_in_status != models.OptInStatus.OPTED_OUT:
                        db_customer.sms_opt_in_status = models.OptInStatus.OPTED_OUT
                        # Create a new ConsentLog for this global opt-out
                        new_log = ConsentLog(
                            customer_id=db_customer.id, business_id=business.id, method="sms_reply_global_stop",
                            phone_number=db_customer.phone, message_sid=message_sid,
                            status=models.OptInStatus.OPTED_OUT.value, replied_at=current_time
                        )
                        self.db.add(new_log)
                        # self.db.commit()
                        logger.info(f"[ConsentService] Customer {db_customer.id} OPTED OUT via global keyword '{sms_body}'. New Log created.")
                        return PlainTextResponse("You have successfully been unsubscribed. You will not receive any more messages from this number. Reply START to resubscribe.", status_code=status.HTTP_200_OK)
                    else:
                        logger.info(f"[ConsentService] Customer {db_customer.id} already opted out. Received global opt-out keyword '{sms_body}'.")
                        return PlainTextResponse("You are already unsubscribed.", status_code=status.HTTP_200_OK) # Or no response
                elif "start" in opt_in_keywords and normalized_response == "start": # Specifically handle START for re-opt-in
                     if db_customer.sms_opt_in_status == models.OptInStatus.OPTED_OUT:
                        db_customer.sms_opt_in_status = models.OptInStatus.OPTED_IN
                        new_log = ConsentLog(
                            customer_id=db_customer.id, business_id=business.id, method="sms_reply_global_start",
                            phone_number=db_customer.phone, message_sid=message_sid,
                            status=models.OptInStatus.OPTED_IN.value, replied_at=current_time
                        )
                        self.db.add(new_log)
                        # self.db.commit()
                        logger.info(f"[ConsentService] Customer {db_customer.id} RE-OPTED IN via global keyword '{sms_body}'. New Log created.")
                        return PlainTextResponse("You have successfully resubscribed. Reply STOP to unsubscribe.", status_code=status.HTTP_200_OK)
                
                logger.info(f"[ConsentService] SMS response '{sms_body}' from Customer {db_customer.id} not a consent keyword and no pending log. Allowing other services to handle.")
                return None # Not a consent keyword, and no pending log to update.

        except Exception as e:
            logger.error(f"[ConsentService] Error processing SMS response from Customer {db_customer.id if 'db_customer' in locals() and db_customer else 'unknown'}: {e}", exc_info=True)
            # self.db.rollback() # Rollback should be handled by the calling route to avoid issues with session state
            return None # Indicate error or let exception propagate if not caught by route


    async def check_consent(self, phone_number: str, business_id: int) -> bool:
        try:
            customer = self.db.query(Customer).filter(
                Customer.phone == phone_number,
                Customer.business_id == business_id
            ).first()
            if not customer: return False
            return customer.opted_in
        except Exception as e:
            logger.error(f"[ConsentService] Error checking consent for {phone_number}, business {business_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to check consent status")

    # Corrected Type Hint: Use lowercase list and dict for Python 3.9+ compatibility
    async def get_consent_history(self, customer_id: int, business_id: int) -> list[dict[str, Any]]:
        try:
            logs = self.db.query(ConsentLog).filter(
                ConsentLog.customer_id == customer_id,
                ConsentLog.business_id == business_id
            ).order_by(desc(ConsentLog.sent_at)).all() # Added desc import
            return [
                {
                    "id": log.id, "status": log.status, "method": log.method,
                    "sent_at": log.sent_at, "replied_at": log.replied_at,
                    "message_sid": log.message_sid
                } for log in logs
            ]
        except Exception as e:
            logger.error(f"[ConsentService] Error getting consent history for cust {customer_id}, biz {business_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get consent history")


    async def handle_opt_in(self, phone_number: str, business_id: int, customer_id: int, method: str = "manual_override") -> ConsentLog:
        logger.info(f"[ConsentService] Manually handling opt-in for customer {customer_id} by {method}.")
        customer = self.db.query(Customer).filter(Customer.id == customer_id, Customer.business_id == business_id).first()
        if not customer:
            raise ValueError(f"Customer {customer_id} not found for business {business_id}")

        customer.opted_in = True
        customer.opted_in_at = datetime.now(timezone.utc)

        consent_log = ConsentLog(
            phone_number=phone_number, business_id=business_id, customer_id=customer_id,
            status="opted_in", method=method,
            replied_at=datetime.now(timezone.utc),
            sent_at=datetime.now(timezone.utc) # Consider if sent_at is appropriate here
        )
        self.db.add(customer) # Ensure customer changes are staged
        self.db.add(consent_log)
        try:
            self.db.commit()
            self.db.refresh(consent_log)
            # self.db.refresh(customer) # Refresh customer if its changes are critical for immediate use
            return consent_log
        except Exception as e:
            self.db.rollback()
            logger.error(f"[ConsentService] Error during manual opt-in for customer {customer_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to record opt-in")


    async def handle_opt_out(self, phone_number: str, business_id: int, customer_id: int, method: str = "manual_override") -> ConsentLog:
        logger.info(f"[ConsentService] Manually handling opt-out for customer {customer_id} by {method}.")
        customer = self.db.query(Customer).filter(Customer.id == customer_id, Customer.business_id == business_id).first()
        if not customer:
            raise ValueError(f"Customer {customer_id} not found for business {business_id}")

        customer.opted_in = False
        # customer.opted_in_at = None # Optionally clear opt-in timestamp

        consent_log = ConsentLog(
            phone_number=phone_number, business_id=business_id, customer_id=customer_id,
            status="opted_out", method=method,
            replied_at=datetime.now(timezone.utc),
            sent_at=datetime.now(timezone.utc) # Consider if sent_at is appropriate
        )
        self.db.add(customer) # Ensure customer changes are staged
        self.db.add(consent_log)
        try:
            self.db.commit()
            self.db.refresh(consent_log)
            # self.db.refresh(customer)
            return consent_log
        except Exception as e:
            self.db.rollback()
            logger.error(f"[ConsentService] Error during manual opt-out for customer {customer_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to record opt-out")


    async def send_opt_in_sms(self, phone_number: str, business_id: int, customer_id: int) -> Dict[str, Any]:
        """
        Sends a personalized opt-in SMS (e.g., for resend). Fetches customer name internally.
        """
        logger.info(f"[ConsentService] Preparing opt-in SMS for customer {customer_id}, business {business_id}.")
        try:
            business = self.db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
            if not business:
                logger.error(f"[ConsentService] Business (ID: {business_id}) not found for send_opt_in_sms.")
                raise ValueError(f"Business not found with ID {business_id}")

            customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
            if not customer:
                logger.error(f"[ConsentService] Customer (ID: {customer_id}) not found for send_opt_in_sms.")
                raise ValueError(f"Customer not found with ID {customer_id}")

            rep_name = business.representative_name or business.business_name
            greeting_name = customer.customer_name or "there"

            message_content = (
                f"Hi {greeting_name}, this is {rep_name} from {business.business_name}. "
                f"We'd love to send you helpful updates and offers! "
                f"To join, please reply YES.\n\n"
                f"We respect your privacy. Msg&Data rates may apply. Reply STOP to unsubscribe."
            )

            sid = await self.twilio_service.send_sms(
                to=phone_number, 
                message_body=message_content, 
                business=business,
                is_direct_reply=True
            )

            if not sid:
                logger.error(f"[ConsentService] Twilio failed to send opt-in SMS to {phone_number} (Cust {customer_id}).")
                return {"success": False, "message_sid": None, "error": "SMS provider failed to send."}

            logger.info(f"[ConsentService] Opt-in SMS sent to {phone_number} (Cust {customer_id}). SID: {sid}")
            # Note: This method doesn't create a ConsentLog. The calling route should handle that if it's a new request.
            return {"success": True, "message_sid": sid}

        except ValueError as ve:
            logger.error(f"[ConsentService] Value error in send_opt_in_sms: {ve}")
            return {"success": False, "message": str(ve)} # Return the error message
        except Exception as e:
            logger.error(f"[ConsentService] Unexpected error in send_opt_in_sms for {phone_number}: {e}", exc_info=True)
            self.db.rollback() # Rollback any potential DB changes if this method did any
            return {"success": False, "message": "An unexpected server error occurred."}