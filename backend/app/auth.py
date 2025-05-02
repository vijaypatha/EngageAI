from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BusinessProfile
from app.schemas import BusinessProfile
from typing import Optional

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[BusinessProfile]:
    # For now, we'll return a dummy user
    # In a real application, you would:
    # 1. Verify the token
    # 2. Get the user from the database
    # 3. Return the user or raise an exception
    user = db.query(BusinessProfile).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return BusinessProfile.from_orm(user) 