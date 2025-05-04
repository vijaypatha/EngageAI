# backend/app/routes/auth_routes.py

# BUSINESS OWNER PERSPECTIVE:
# This file implements phone-based authentication for businesses via SMS OTP verification.
# It provides secure access to the platform by verifying your business's phone number and
# establishing a persistent login session. This ensures that only authorized users can access
# business data and send messages to customers, protecting both business and customer information.

# DEVELOPER PERSPECTIVE:
# Route:
# - POST /auth/request-otp - Sends OTP to phone number
# - POST /auth/verify-otp - Verifies OTP code
# - POST /auth/session - Creates a session after verification
# - GET /auth/me - Gets current logged-in business profile
# - POST /auth/logout - Ends the current session
#
# Services Used: TwilioService (for sending OTP messages)
#
# Frontend Usage:
# - Used during onboarding (frontend/src/app/onboarding/page.tsx) for phone verification
# - Session is managed via cookies (set by SessionMiddleware in main.py)
# - Auth state determines UI components visibility (ClientLayout.tsx, Navigation.tsx)
#
# Security Notes:
# - Uses in-memory OTP storage (should be replaced with Redis in production)
# - Implements rate limiting (3 attempts max)
# - 5-minute OTP expiration
# - Session-based auth with cookies rather than JWT


from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BusinessProfile
from pydantic import BaseModel
import random
import string
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging # <<< Ensure logging is imported
from app.services.twilio_service import TwilioService

# Configure logging
logger = logging.getLogger(__name__) # <<< Ensure logger is initialized

router = APIRouter(tags=["auth"])

# In-memory storage for OTPs (replace with Redis in production)
otp_storage: Dict[str, Dict[str, any]] = {}

class OTPRequest(BaseModel):
    phone_number: str

class OTPVerify(BaseModel):
    phone_number: str
    otp: str

def generate_otp() -> str:
    """Generate a 6-digit OTP."""
    return ''.join(random.choices(string.digits, k=6))

@router.post("/request-otp")
async def request_otp(
    request: OTPRequest,
    db: Session = Depends(get_db)
):
    """Request OTP for authentication."""
    # Generate OTP
    otp = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    # Store OTP
    otp_storage[request.phone_number] = {
        'otp': otp,
        'expires_at': expires_at,
        'attempts': 0
    }
    logger.info(f"Generated OTP for {request.phone_number}: {otp_storage[request.phone_number]}") # Added log

    # Send OTP via Twilio service
    try:
        twilio_service = TwilioService(db)
        await twilio_service.send_otp(request.phone_number, otp)
        return {"message": "OTP sent successfully"}
    except Exception as e:
        logger.error(f"Failed to send OTP to {request.phone_number}: {str(e)}", exc_info=True) # Added exc_info
        raise HTTPException(status_code=500, detail="Failed to send OTP")

# =====================================================
# START: /verify-otp with enhanced logging
# =====================================================
@router.post("/verify-otp")
async def verify_otp(
    request: OTPVerify,
    db: Session = Depends(get_db)
):
    """Verify OTP and start session."""
    logger.info(f"--- Verifying OTP ---")
    logger.info(f"Received phone: {request.phone_number}, Received OTP: {request.otp}")

    stored_otp_data = otp_storage.get(request.phone_number)
    # Log the raw storage for debugging comparison
    logger.info(f"Raw otp_storage state: {otp_storage}") 
    logger.info(f"Data found in otp_storage for key '{request.phone_number}': {stored_otp_data}") # Log the whole dict found

    if not stored_otp_data:
         logger.warning("OTP data not found in storage for the provided phone number key.")
         raise HTTPException(status_code=400, detail="OTP not found or expired") # Keep generic message for security

    # Log details before comparison
    stored_code = stored_otp_data.get('otp')
    stored_expiry = stored_otp_data.get('expires_at')
    stored_attempts = stored_otp_data.get('attempts', 0) # Use .get with default
    
    # Handle potential None expiry before comparison
    is_expired = True # Default to expired if expiry is missing
    if stored_expiry:
        is_expired = datetime.utcnow() > stored_expiry
    
    logger.info(f"Stored code: {stored_code}, Expected code (from request): {request.otp}")
    logger.info(f"Stored expiry: {stored_expiry}, Current UTC time: {datetime.utcnow()}, Is expired: {is_expired}")
    logger.info(f"Stored attempts: {stored_attempts}")

    # --- Validation Checks ---
    if is_expired:
        logger.warning("OTP expired based on timestamp comparison.")
        # Attempt to clean up expired OTP from storage
        if request.phone_number in otp_storage:
             try:
                 del otp_storage[request.phone_number]
                 logger.info(f"Deleted expired OTP data for {request.phone_number}")
             except KeyError:
                 logger.warning(f"Tried to delete expired OTP for {request.phone_number}, but key was already gone.")
        raise HTTPException(status_code=400, detail="OTP expired")

    if stored_attempts >= 3:
        logger.warning("Max attempts reached.")
        # Attempt to clean up locked OTP from storage
        if request.phone_number in otp_storage:
            try:
                del otp_storage[request.phone_number]
                logger.info(f"Deleted maxed-attempt OTP data for {request.phone_number}")
            except KeyError:
                logger.warning(f"Tried to delete maxed-attempt OTP for {request.phone_number}, but key was already gone.")
        raise HTTPException(status_code=400, detail="Too many attempts") # Keep generic message

    if request.otp != stored_code:
        logger.warning(f"OTP mismatch: Received '{request.otp}', Expected '{stored_code}'")
        # Increment attempts - SAFELY
        current_attempts = stored_attempts + 1
        # Ensure the key still exists before trying to update
        if request.phone_number in otp_storage:
            otp_storage[request.phone_number]['attempts'] = current_attempts # Update storage
            logger.info(f"Attempt count incremented to {current_attempts} for {request.phone_number}")
        else:
            logger.warning(f"Attempted to increment attempts for {request.phone_number}, but key no longer exists in otp_storage.")
            # If key doesn't exist, it's effectively expired or invalid anyway
            raise HTTPException(status_code=400, detail="OTP not found or expired")
            
        raise HTTPException(status_code=400, detail="Invalid OTP")

    # --- Success Path ---
    logger.info("OTP Verified Successfully!")
    # Clean up successful OTP from storage
    if request.phone_number in otp_storage:
        try:
            del otp_storage[request.phone_number]
            logger.info(f"Deleted verified OTP data for {request.phone_number}")
        except KeyError:
            logger.warning(f"Tried to delete verified OTP for {request.phone_number}, but key was already gone.")
    else:
         logger.warning(f"Verified OTP for {request.phone_number}, but key was already missing from otp_storage.")


    # Get business profile for the phone number
    logger.info(f"Looking up business profile for phone: {request.phone_number}")
    business = db.query(BusinessProfile).filter_by(business_phone_number=request.phone_number).first()
    if not business:
        logger.error(f"Business profile not found for verified phone number {request.phone_number}")
        # Even though OTP was right, if no profile exists, it's an issue.
        # Should this be 404 or 400? Let's use 404 as the profile is missing.
        raise HTTPException(status_code=404, detail="Business profile not found")

    logger.info(f"Found business profile ID: {business.id} for phone: {request.phone_number}")
    return {
        "message": "OTP verified successfully",
        "business_id": business.id
    }
# =====================================================
# END: /verify-otp with enhanced logging
# =====================================================

# ✅ Store session using SessionMiddleware
# Define a Pydantic model for the /session request body
class SessionCreateBody(BaseModel):
    business_id: int

# Corrected /session endpoint
@router.post("/session")
def create_session(
    request: Request, # Keep Request for session access
    payload: SessionCreateBody, # <<< Use Pydantic model for body
    db: Session = Depends(get_db) # Keep DB access
):
    """Create a new session for authenticated business."""
    # Access business_id from the payload
    business_id = payload.business_id
    business = db.query(BusinessProfile).filter_by(id=business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Set session data
    request.session["business_id"] = business.id
    # Optionally add other info like name, slug etc. if needed often
    # request.session["business_slug"] = business.slug
    logger.info(f"Session created for business_id: {business.id}")
    return {"message": "Session started", "business_id": business.id}

# ✅ Read session
@router.get("/me")
def get_me(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current authenticated business profile."""
    business_id = request.session.get("business_id")
    if not business_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    business = db.query(BusinessProfile).filter_by(id=business_id).first()
    if not business:
        # If session has an ID but profile is gone, clear session and raise 401
        request.session.clear()
        raise HTTPException(status_code=401, detail="Not authenticated (business not found)")

    # Return relevant, non-sensitive info
    return {
        "business_id": business.id,
        "business_name": business.business_name,
        "slug": business.slug # Added slug as it's useful for frontend routing
        }

# ✅ Optional logout
@router.post("/logout")
def logout(request: Request):
    """Clear current session."""
    business_id = request.session.get("business_id")
    request.session.clear()
    logger.info(f"Session cleared for business_id: {business_id if business_id else 'N/A'}")
    return {"message": "Logged out"}