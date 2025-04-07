from fastapi import APIRouter, Response, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BusinessProfile

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE_NAME = "session_business_id"

# ✅ Set session cookie after business creation
@router.post("/session")
def create_session(business_id: int, response: Response, db: Session = Depends(get_db)):
    business = db.query(BusinessProfile).filter_by(id=business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=str(business.id),
        httponly=True,
        samesite="lax"
    )
    return {"message": "Session started", "business_id": business.id}

# ✅ Fetch business from session cookie
@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    business_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not business_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    business = db.query(BusinessProfile).filter_by(id=business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    return {"business_id": business.id, "business_name": business.business_name}

# ✅ (Optional) Clear cookie
@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"message": "Logged out"}
