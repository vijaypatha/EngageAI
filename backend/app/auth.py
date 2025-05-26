import logging
from fastapi import Depends, HTTPException, status, Request # Added Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import models # Import your models module
from app.database import get_async_db # For DB access
# from app.config import settings # SECRET_KEY is used by SessionMiddleware, not directly here for decryption

logger = logging.getLogger(__name__)

async def get_current_authenticated_business(
    request: Request, # Inject the current request object to access the session
    db: AsyncSession = Depends(get_async_db)
) -> models.BusinessProfile:
    """
    Retrieves the authenticated BusinessProfile from the server-side session
    which was established after OTP verification.
    """
    logger.debug(f"Auth: Attempting to get business from session. Session keys: {list(request.session.keys()) if hasattr(request, 'session') else 'No session'}")

    if not hasattr(request, "session") or not request.session:
        logger.warning("Auth: No active session found on the request.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated (no session). Please log in.",
        )

    business_id_from_session = request.session.get("business_id")
    session_slug = request.session.get("business_slug") # You also store slug

    if not business_id_from_session:
        logger.warning("Auth: 'business_id' not found in session.")
        # It's good practice to clear a session if it's malformed or missing key data
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session: Business ID missing. Please log in again.",
        )

    try:
        business_id = int(business_id_from_session)
    except ValueError:
        logger.error(f"Auth: 'business_id' in session is not a valid integer: {business_id_from_session}")
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session data format. Please log in again.",
        )

    # Fetch the business from DB to ensure it still exists and is valid
    business = await db.get(models.BusinessProfile, business_id)
    if not business:
        logger.warning(f"Auth: Business with ID {business_id} from session not found in database.")
        request.session.clear() # Clear session if business doesn't exist
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, # Or 403 if you prefer, as session might be stale
            detail="Authenticated business not found or session invalid. Please log in again.",
        )

    # Optional: Validate slug if it's critical for this check
    if session_slug and business.slug != session_slug:
        logger.warning(f"Auth: Session slug '{session_slug}' does not match DB slug '{business.slug}' for business ID {business_id}.")
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, # Or 403
            detail="Session data mismatch. Please log in again.",
        )
        
    # You might add other checks here, e.g., if business.is_active
    
    logger.info(f"Auth: Successfully authenticated business: {business.business_name} (ID: {business.id}) from session.")
    return business

# You can remove the old placeholder get_current_user and oauth2_scheme if they are not used elsewhere.
# If they are used for a different type of user (e.g., admin users via a different login), keep them.
# For business authentication via OTP and session, get_current_authenticated_business is the relevant one.