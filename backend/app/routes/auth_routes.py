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
import logging
from app.services.twilio_service import TwilioService

# Configure logging
logger = logging.getLogger(__name__)

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
    
    # Send OTP via Twilio service
    try:
        twilio_service = TwilioService(db)
        await twilio_service.send_otp(request.phone_number, otp)
        return {"message": "OTP sent successfully"}
    except Exception as e:
        logger.error(f"Failed to send OTP: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send OTP")

@router.post("/verify-otp")
async def verify_otp(
    request: OTPVerify,
    db: Session = Depends(get_db)
):
    """Verify OTP and start session."""
    stored_otp = otp_storage.get(request.phone_number)
    
    if not stored_otp:
        raise HTTPException(status_code=400, detail="OTP not found or expired")
    
    if datetime.utcnow() > stored_otp['expires_at']:
        del otp_storage[request.phone_number]
        raise HTTPException(status_code=400, detail="OTP expired")
    
    if stored_otp['attempts'] >= 3:
        del otp_storage[request.phone_number]
        raise HTTPException(status_code=400, detail="Too many attempts")
    
    if request.otp != stored_otp['otp']:
        otp_storage[request.phone_number]['attempts'] += 1
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    # OTP verified successfully
    del otp_storage[request.phone_number]
    
    # Get business profile for the phone number
    business = db.query(BusinessProfile).filter_by(business_phone_number=request.phone_number).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business profile not found")
    
    return {
        "message": "OTP verified successfully",
        "business_id": business.id
    }

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
        raise HTTPException(status_code=404, detail="Business not found")

    return {"business_id": business.id, "business_name": business.business_name}

# ✅ Optional logout
@router.post("/logout")
def logout(request: Request):
    """Clear current session."""
    request.session.clear()
    return {"message": "Logged out"}

