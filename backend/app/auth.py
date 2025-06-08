# backend/app/auth.py
from fastapi import Depends, HTTPException, status, Request # Added Request
# from fastapi.security import OAuth2PasswordBearer # OAuth2PasswordBearer might no longer be needed if solely using sessions for this
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BusinessProfile as BusinessProfileModel
from app.schemas import BusinessProfile as BusinessProfileSchema # Use your Pydantic schema
from typing import Optional

# If you are ONLY using session-based auth via request.session for get_current_user,
# then oauth2_scheme might not be needed here.
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(
    request: Request, # Depend on the Request object to access the session
    db: Session = Depends(get_db)
) -> Optional[BusinessProfileSchema]:
    business_id = request.session.get("business_id")

    if not business_id:
        # No business_id in session, so user is not authenticated via session
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated (no active session)",
            # headers={"WWW-Authenticate": "Bearer"}, # Not strictly needed if not using Bearer scheme here
        )

    user_orm = db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()

    if not user_orm:
        # business_id was in session, but no matching business found in DB (should be rare if session is managed correctly)
        # Clear the invalid session to prevent further issues
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session: Business profile not found",
        )
    
    return BusinessProfileSchema.from_orm(user_orm)