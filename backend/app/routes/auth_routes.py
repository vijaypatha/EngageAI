# backend/app/routes/auth_routes.py

# BUSINESS OWNER PERSPECTIVE:
# This file implements phone-based authentication for businesses via SMS OTP verification.
# It provides secure access to the platform by verifying your business's phone number and
# establishing a persistent login session. This ensures that only authorized users can access
# business data and send messages to customers, protecting both business and customer information.

# DEVELOPER PERSPECTIVE:
# Routes:
# - POST /auth/request-otp - Sends OTP to phone number.
# - POST /auth/verify-otp - Verifies OTP code and returns business_id and slug.
# - POST /auth/session - Creates a session after verification, storing business_id and slug.
# - GET /auth/me - Gets current logged-in business profile, including business_id, name, and slug.
# - POST /auth/logout - Ends the current session.
#
# Services Used: TwilioService (for sending OTPs via Twilio)
#
# Frontend Usage:
# - Used during onboarding and login for phone verification.
# - Session is managed via cookies (set by SessionMiddleware in main.py).
# - Auth state (including slug) determines UI components visibility and navigation.
#
# Security Notes:
# - Uses in-memory OTP storage (should be replaced with Redis in production for scalability and persistence).
# - Implements rate limiting (3 attempts max) and 5-minute OTP expiration.
# - Session-based auth with cookies.

# backend/app/routes/auth_routes.py

from fastapi import APIRouter, Request, HTTPException, Depends, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, validator # Added validator
import random
import string
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

from app.database import get_db
from app.models import BusinessProfile # Import the BusinessProfile model
from app.schemas import normalize_phone_number # Import the normalize_phone_number function
from app.services.twilio_service import TwilioService # Service for sending OTPs
from app.config import settings # Import settings to check DEBUG mode

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# In-memory storage for OTPs.
# IMPORTANT: For production, replace this with a persistent and scalable solution like Redis.
otp_storage: Dict[str, Dict[str, any]] = {}

# --- Pydantic Models ---
class OTPRequest(BaseModel):
    phone_number: str
    _normalize_otp_phone = validator('phone_number', pre=True, allow_reuse=True)(normalize_phone_number)

class OTPVerify(BaseModel):
    phone_number: str
    otp: str
    _normalize_verify_phone = validator('phone_number', pre=True, allow_reuse=True)(normalize_phone_number)

class SessionCreateBody(BaseModel):
    business_id: int

# --- Helper Functions ---
def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP of a specified length."""
    return ''.join(random.choices(string.digits, k=length))

# --- Development/Test Constants (Magic OTP) ---
DEV_MAGIC_OTP = "000000"
try:
    DEV_TEST_PHONE_NUMBER_NORMALIZED = normalize_phone_number("+15551001234")
except ValueError:
    DEV_TEST_PHONE_NUMBER_NORMALIZED = "+15551001234" # Fallback, though normalization should work

# --- API Endpoints ---
@router.post("/request-otp", status_code=status.HTTP_200_OK)
async def request_otp(
    request_data: OTPRequest,
    db: Session = Depends(get_db)
):
    phone_number = request_data.phone_number
    otp_code = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    otp_storage[phone_number] = {
        'otp': otp_code,
        'expires_at': expires_at,
        'attempts': 0
    }
    logger.info(f"Generated OTP {otp_code} for {phone_number}, expires at {expires_at}.")

    # Log OTP to console if in DEBUG mode for easy testing with dummy numbers
    if settings.DEBUG:
        logger.info(f"DEBUG MODE: OTP for {phone_number} is {otp_code}")

    try:
        twilio_service = TwilioService(db) # TwilioService requires db session
        # Even if it's a dummy number, TwilioService might try to send.
        # For true dummy numbers, Twilio will likely fail, which is fine for dev.
        # If TwilioService.send_otp raises an exception on invalid numbers and you want to avoid that for dummy numbers:
        if phone_number == DEV_TEST_PHONE_NUMBER_NORMALIZED and settings.DEBUG:
            logger.info(f"DEV MODE: Skipping actual SMS send for dummy number {phone_number}. OTP is '{otp_code}'.")
        else:
            await twilio_service.send_otp(phone_number, otp_code)
        
        logger.info(f"OTP dispatch process initiated for {phone_number}.")
        return {"message": "OTP sent successfully (or logged for dev if dummy number)"}
    except Exception as e:
        logger.error(f"Failed to send OTP to {phone_number}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send OTP. Please try again later.")

@router.post("/verify-otp", status_code=status.HTTP_200_OK)
async def verify_otp(
    request_data: OTPVerify,
    db: Session = Depends(get_db)
):
    phone_number = request_data.phone_number
    submitted_otp = request_data.otp

    logger.info(f"Attempting OTP verification for phone: {phone_number} with OTP: {submitted_otp}")

    # --- Development Magic OTP Check ---
    if settings.DEBUG and \
       phone_number == DEV_TEST_PHONE_NUMBER_NORMALIZED and \
       submitted_otp == DEV_MAGIC_OTP:
        
        logger.info(f"Magic OTP '{DEV_MAGIC_OTP}' used for dev phone number {phone_number}. Bypassing normal OTP check.")
        
        if phone_number in otp_storage: # Clean up any "real" OTP stored for this number
            del otp_storage[phone_number]
            logger.info(f"Removed any stored OTP from otp_storage for {phone_number} due to magic OTP usage.")

        business = db.query(BusinessProfile).filter(BusinessProfile.business_phone_number == phone_number).first()
        
        if not business:
            logger.error(f"Magic OTP: No business profile found for verified dev phone number {phone_number}.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile for this dev phone number not found.")
        if not business.slug:
            logger.error(f"Magic OTP: Business profile (ID: {business.id}) is missing a slug.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Business profile configuration error (slug missing).")

        logger.info(f"Magic OTP: Successfully retrieved business profile (ID: {business.id}, Slug: {business.slug}) for phone: {phone_number}")
        return {
            "message": "OTP verified successfully (using magic OTP for development)",
            "business_id": business.id,
            "slug": business.slug
        }
    # --- End Development Magic OTP Check ---

    stored_otp_data = otp_storage.get(phone_number)

    if not stored_otp_data:
        logger.warning(f"No OTP data found in storage for {phone_number}.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP or OTP expired.")

    stored_code = stored_otp_data.get('otp')
    stored_expiry = stored_otp_data.get('expires_at')
    stored_attempts = stored_otp_data.get('attempts', 0)

    is_expired = True 
    if isinstance(stored_expiry, datetime):
        is_expired = datetime.utcnow() > stored_expiry
    else:
        logger.error(f"Stored expiry for {phone_number} is not a datetime object: {stored_expiry}")

    if is_expired:
        logger.warning(f"OTP for {phone_number} has expired.")
        if phone_number in otp_storage:
            del otp_storage[phone_number]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired. Please request a new one.")

    if stored_attempts >= 3:
        logger.warning(f"Maximum OTP attempts reached for {phone_number}.")
        if phone_number in otp_storage:
            del otp_storage[phone_number]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many invalid OTP attempts. Please request a new one.")

    if submitted_otp != stored_code:
        logger.warning(f"Invalid OTP for {phone_number}. Submitted: '{submitted_otp}', Expected: '{stored_code}'")
        if phone_number in otp_storage:
            otp_storage[phone_number]['attempts'] = stored_attempts + 1
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP.")

    # --- OTP Verification Successful (Normal Path) ---
    logger.info(f"OTP successfully verified for {phone_number}.")
    if phone_number in otp_storage:
        del otp_storage[phone_number]
        logger.info(f"Removed verified OTP data for {phone_number} from storage.")

    business = db.query(BusinessProfile).filter(BusinessProfile.business_phone_number == phone_number).first()
    if not business:
        logger.error(f"No business profile found for verified phone number {phone_number}, though OTP was correct.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile associated with this phone number not found.")
    if not business.slug:
        logger.error(f"Business profile (ID: {business.id}, Name: {business.business_name}) is missing a slug.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Business profile configuration error (slug missing).")

    logger.info(f"Successfully retrieved business profile (ID: {business.id}, Slug: {business.slug}) for phone: {phone_number}")
    return {
        "message": "OTP verified successfully",
        "business_id": business.id,
        "slug": business.slug
    }

@router.post("/session", status_code=status.HTTP_200_OK)
def create_session(
    fastapi_request: Request,
    payload: SessionCreateBody,
    db: Session = Depends(get_db)
):
    business_id = payload.business_id
    logger.info(f"Attempting to create session for business_id: {business_id}")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        logger.warning(f"Session creation failed: Business profile not found for ID {business_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found, cannot create session.")
    if not business.slug:
        logger.error(f"Session creation aborted: Business profile (ID: {business.id}) is missing a slug.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Business profile configuration error (slug missing).")

    fastapi_request.session["business_id"] = business.id
    fastapi_request.session["business_slug"] = business.slug
    logger.info(f"Session successfully created for Business ID: {business.id}, Slug: {business.slug}.")
    return {
        "message": "Session started successfully",
        "business_id": business.id,
        "slug": business.slug
    }

@router.get("/me", status_code=status.HTTP_200_OK)
def get_me(
    fastapi_request: Request,
    # `get_current_user` is not used here as this endpoint itself establishes 'me' based on session
    # If this endpoint were to be protected by the same mechanism, it would be redundant.
    # It's common for /me to directly inspect the session.
    db: Session = Depends(get_db)
):
    business_id = fastapi_request.session.get("business_id")
    session_slug = fastapi_request.session.get("business_slug")
    logger.info(f"Fetching '/me' data. Session business_id: {business_id}, Session slug: {session_slug}")

    if not business_id:
        logger.info("No active session found for '/me' (business_id missing).")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated. No active session.")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        logger.warning(f"Active session for business_id {business_id}, but business profile not found in DB. Clearing session.")
        fastapi_request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalid. Business profile not found.")

    if business.slug != session_slug: # Keep session slug up-to-date
        logger.warning(f"Slug mismatch for business_id {business_id}. Session slug: '{session_slug}', DB slug: '{business.slug}'. Updating session slug.")
        fastapi_request.session["business_slug"] = business.slug

    logger.info(f"Successfully retrieved '/me' data for Business ID: {business.id}, Name: {business.business_name}, Slug: {business.slug}")
    return {
        "business_id": business.id,
        "business_name": business.business_name,
        "slug": business.slug
    }

@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    fastapi_request: Request
):
    business_id = fastapi_request.session.get("business_id")
    fastapi_request.session.clear()
    logger.info(f"Session cleared for business_id: {business_id if business_id else 'N/A'}. User logged out.")
    return {"message": "Successfully logged out."}

# from fastapi import APIRouter, Request, HTTPException, Depends, status
# from sqlalchemy.orm import Session
# from app.database import get_db
# from app.models import BusinessProfile # Import the BusinessProfile model
# from pydantic import BaseModel, validator # Added validator
# import random
# import string
# from datetime import datetime, timedelta
# from typing import Dict, Optional
# import logging
# from app.services.twilio_service import TwilioService # Service for sending OTPs via Twilio

# # Import the normalize_phone_number function from schemas
# from app.schemas import normalize_phone_number

# # Configure logging
# logger = logging.getLogger(__name__)

# router = APIRouter(tags=["auth"])

# # In-memory storage for OTPs.
# # IMPORTANT: For production, replace this with a persistent and scalable solution like Redis.
# otp_storage: Dict[str, Dict[str, any]] = {}

# # Pydantic model for the OTP request body
# class OTPRequest(BaseModel):
#     phone_number: str

#     # Apply the imported validator
#     _normalize_otp_phone = validator('phone_number', pre=True, allow_reuse=True)(normalize_phone_number)


# # Pydantic model for the OTP verification body
# class OTPVerify(BaseModel):
#     phone_number: str
#     otp: str

#     # Apply the imported validator
#     _normalize_verify_phone = validator('phone_number', pre=True, allow_reuse=True)(normalize_phone_number)


# # Pydantic model for the session creation body
# class SessionCreateBody(BaseModel):
#     business_id: int

# def generate_otp(length: int = 6) -> str:
#     """Generate a numeric OTP of a specified length."""
#     return ''.join(random.choices(string.digits, k=length))

# @router.post("/request-otp", status_code=status.HTTP_200_OK)
# async def request_otp(
#     request_data: OTPRequest, # Changed variable name for clarity
#     db: Session = Depends(get_db)
# ):
#     """
#     Generates an OTP, stores it, and sends it to the provided phone number via SMS.
#     """
#     # phone_number will already be normalized by the Pydantic validator
#     phone_number = request_data.phone_number
#     otp_code = generate_otp()
#     expires_at = datetime.utcnow() + timedelta(minutes=5) # OTP expires in 5 minutes

#     # Store OTP details (otp, expiry, attempts)
#     # Use the normalized phone_number as the key
#     otp_storage[phone_number] = {
#         'otp': otp_code,
#         'expires_at': expires_at,
#         'attempts': 0
#     }
#     logger.info(f"Generated OTP {otp_code} for {phone_number}, expires at {expires_at}. Stored: {otp_storage[phone_number]}")

#     # Send OTP using Twilio service
#     try:
#         twilio_service = TwilioService(db)
#         await twilio_service.send_otp(phone_number, otp_code)
#         logger.info(f"OTP SMS successfully dispatched to {phone_number}.")
#         return {"message": "OTP sent successfully"}
#     except Exception as e:
#         logger.error(f"Failed to send OTP to {phone_number}: {str(e)}", exc_info=True)
#         # Do not expose detailed error to client for security
#         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send OTP. Please try again later.")

# @router.post("/verify-otp", status_code=status.HTTP_200_OK)
# async def verify_otp(
#     request_data: OTPVerify, # Changed variable name for clarity
#     db: Session = Depends(get_db)
# ):
#     """
#     Verifies the provided OTP against the stored OTP for the phone number.
#     Returns business_id and slug upon successful verification.
#     """
#     # phone_number will already be normalized by the Pydantic validator
#     phone_number = request_data.phone_number
#     submitted_otp = request_data.otp

#     logger.info(f"Attempting OTP verification for phone: {phone_number} with OTP: {submitted_otp}")

#     # Use the normalized phone_number to look up in otp_storage
#     stored_otp_data = otp_storage.get(phone_number)

#     # Log the state of otp_storage for debugging if needed
#     # logger.debug(f"Current otp_storage state: {otp_storage}")
#     logger.info(f"Retrieved stored OTP data for '{phone_number}': {stored_otp_data}")

#     if not stored_otp_data:
#          logger.warning(f"No OTP data found in storage for {phone_number}.")
#          # Generic message to prevent revealing if a phone number is in the system
#          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP or OTP expired.")

#     stored_code = stored_otp_data.get('otp')
#     stored_expiry = stored_otp_data.get('expires_at')
#     stored_attempts = stored_otp_data.get('attempts', 0)

#     # Check for expiration
#     is_expired = True # Default to expired if 'expires_at' is somehow missing
#     if isinstance(stored_expiry, datetime):
#         is_expired = datetime.utcnow() > stored_expiry
#     else:
#         logger.error(f"Stored expiry for {phone_number} is not a datetime object: {stored_expiry}")


#     logger.info(f"Comparing OTP for {phone_number}: Submitted='{submitted_otp}', Stored='{stored_code}'. Expiry={stored_expiry}, Now={datetime.utcnow()}, Expired={is_expired}. Attempts={stored_attempts}")

#     if is_expired:
#         logger.warning(f"OTP for {phone_number} has expired.")
#         if phone_number in otp_storage: # Clean up expired OTP
#              del otp_storage[phone_number]
#              logger.info(f"Removed expired OTP data for {phone_number} from storage.")
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired. Please request a new one.")

#     if stored_attempts >= 3: # Max 3 attempts
#         logger.warning(f"Maximum OTP attempts reached for {phone_number}.")
#         if phone_number in otp_storage: # Clean up OTP after max attempts
#             del otp_storage[phone_number]
#             logger.info(f"Removed OTP data for {phone_number} from storage after max attempts.")
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many invalid OTP attempts. Please request a new one.")

#     if submitted_otp != stored_code:
#         logger.warning(f"Invalid OTP for {phone_number}. Submitted: '{submitted_otp}', Expected: '{stored_code}'")
#         # Increment attempts; ensure key exists before updating
#         if phone_number in otp_storage:
#             otp_storage[phone_number]['attempts'] = stored_attempts + 1
#             logger.info(f"OTP attempt count for {phone_number} incremented to {otp_storage[phone_number]['attempts']}.")
#         else:
#             # This case (key disappearing during check) is unlikely but handled for robustness
#             logger.warning(f"Attempted to increment attempts for {phone_number}, but key was already removed from otp_storage.")
#             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP not found or expired.")
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP.")

#     # --- OTP Verification Successful ---
#     logger.info(f"OTP successfully verified for {phone_number}.")
#     if phone_number in otp_storage: # Clean up successful OTP
#         del otp_storage[phone_number]
#         logger.info(f"Removed verified OTP data for {phone_number} from storage.")

#     # Retrieve business profile using the verified (and normalized) phone number
#     logger.info(f"Fetching business profile for phone number: {phone_number}")
#     business = db.query(BusinessProfile).filter(BusinessProfile.business_phone_number == phone_number).first()

#     if not business:
#         logger.error(f"No business profile found for verified phone number {phone_number}, though OTP was correct.")
#         # This indicates a data inconsistency or an attempt to verify OTP for a non-existent business phone.
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile associated with this phone number not found.")

#     if not business.slug:
#         logger.error(f"Business profile (ID: {business.id}, Name: {business.business_name}) is missing a slug. This is required for navigation.")
#         # This is a critical configuration issue for the business.
#         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Business profile configuration error (slug missing). Please contact support.")

#     logger.info(f"Successfully retrieved business profile (ID: {business.id}, Slug: {business.slug}) for phone: {phone_number}")
#     return {
#         "message": "OTP verified successfully",
#         "business_id": business.id,
#         "slug": business.slug  # Return the slug for frontend navigation
#     }

# @router.post("/session", status_code=status.HTTP_200_OK)
# def create_session(
#     fastapi_request: Request, # Renamed to avoid conflict with Pydantic 'request'
#     payload: SessionCreateBody,
#     db: Session = Depends(get_db)
# ):
#     """
#     Creates a new session for an authenticated business.
#     Stores business_id and slug in the session.
#     """
#     business_id = payload.business_id
#     logger.info(f"Attempting to create session for business_id: {business_id}")

#     business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
#     if not business:
#         logger.warning(f"Session creation failed: Business profile not found for ID {business_id}.")
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found, cannot create session.")

#     if not business.slug:
#         logger.error(f"Session creation aborted: Business profile (ID: {business.id}) is missing a slug.")
#         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Business profile configuration error (slug missing).")

#     # Store essential identifiers in the session
#     fastapi_request.session["business_id"] = business.id
#     fastapi_request.session["business_slug"] = business.slug # Store slug
#     # Optionally, store business_name if frequently needed and to avoid DB lookups on /me
#     # fastapi_request.session["business_name"] = business.business_name

#     logger.info(f"Session successfully created for Business ID: {business.id}, Slug: {business.slug}.")
#     return {
#         "message": "Session started successfully",
#         "business_id": business.id,
#         "slug": business.slug # Return slug for immediate use by frontend if needed
#     }

# @router.get("/me", status_code=status.HTTP_200_OK)
# def get_me(
#     fastapi_request: Request, # Renamed to avoid conflict
#     db: Session = Depends(get_db)
# ):
#     """
#     Retrieves the profile of the currently authenticated business from the session.
#     Returns business_id, business_name, and slug.
#     """
#     business_id = fastapi_request.session.get("business_id")
#     # Also retrieve slug from session, which should have been set during /session
#     session_slug = fastapi_request.session.get("business_slug")

#     logger.info(f"Fetching '/me' data. Session business_id: {business_id}, Session slug: {session_slug}")

#     if not business_id:
#         logger.info("No active session found for '/me' (business_id missing).")
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated. No active session.")

#     # Fetch business profile from DB to ensure data is fresh and to validate session.
#     business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()

#     if not business:
#         logger.warning(f"Active session for business_id {business_id}, but business profile not found in DB. Clearing session.")
#         fastapi_request.session.clear() # Clear invalid session
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalid. Business profile not found.")

#     # Ensure the slug from the DB is consistent with the session, or update session if DB is more current.
#     # This handles cases where the slug might have changed since the session was created.
#     if business.slug != session_slug:
#         logger.warning(f"Slug mismatch for business_id {business_id}. Session slug: '{session_slug}', DB slug: '{business.slug}'. Updating session slug.")
#         fastapi_request.session["business_slug"] = business.slug

#     logger.info(f"Successfully retrieved '/me' data for Business ID: {business.id}, Name: {business.business_name}, Slug: {business.slug}")
#     return {
#         "business_id": business.id,
#         "business_name": business.business_name, # For display purposes
#         "slug": business.slug                   # For URL navigation
#     }

# @router.post("/logout", status_code=status.HTTP_200_OK)
# def logout(
#     fastapi_request: Request # Renamed to avoid conflict
# ):
#     """Clears the current session, effectively logging out the business."""
#     business_id = fastapi_request.session.get("business_id") # Get for logging before clearing
#     fastapi_request.session.clear()
#     logger.info(f"Session cleared for business_id: {business_id if business_id else 'N/A'}. User logged out.")
#     return {"message": "Successfully logged out."}