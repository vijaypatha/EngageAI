from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BusinessProfile

router = APIRouter(prefix="/auth", tags=["auth"])

# ✅ Store session using SessionMiddleware
@router.post("/session")
def create_session(request: Request, business_id: int, db: Session = Depends(get_db)):
    business = db.query(BusinessProfile).filter_by(id=business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    request.session["business_id"] = business.id
    return {"message": "Session started", "business_id": business.id}

# ✅ Read session
@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
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
    request.session.clear()
    return {"message": "Logged out"}
