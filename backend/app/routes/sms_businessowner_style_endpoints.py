from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BusinessOwnerStyle
from app.schemas import SMSStyleInput
from app.services.sms_businessowner_style import generate_scenarios

router = APIRouter()

# 🔹 1. Generate scenarios to ask the business owner
@router.get("/sms-style/scenarios/{business_id}")
def get_scenarios(business_id: int, db: Session = Depends(get_db)):
    scenarios = generate_scenarios(business_id, db)
    return {"scenarios": scenarios}

# 🔹 2. Capture multiple business owner tone responses (Q&A pairs)
from typing import List
from app.schemas import SMSStyleInput

@router.post("/sms-style")
def capture_multiple_sms_styles(styles: List[SMSStyleInput], db: Session = Depends(get_db)):
    for sms_style in styles:
        db.add(BusinessOwnerStyle(
            business_id=sms_style.business_id,
            scenario=sms_style.scenario,
            response=sms_style.response
        ))
    db.commit()
    return {"message": "All styles saved successfully"}


# 🔹 3. List all tone examples for this business
@router.get("/sms-style/{business_id}")
def list_owner_style(business_id: int, db: Session = Depends(get_db)):
    styles = db.query(BusinessOwnerStyle).filter_by(business_id=business_id).all()
    return [
        {"id": style.id, "scenario": style.scenario, "response": style.response}
        for style in styles
    ]

# ➕ Alias to support frontend path expectation
@router.get("/sms-style/response/{business_id}")
def alias_list_owner_style(business_id: int, db: Session = Depends(get_db)):
    styles = db.query(BusinessOwnerStyle).filter_by(business_id=business_id).all()
    return [
        {"id": style.id, "scenario": style.scenario, "response": style.response}
        for style in styles
    ]


# ✏️ 4. Edit a saved tone response
@router.put("/sms-style/{id}")
def update_owner_style(id: int, data: SMSStyleInput, db: Session = Depends(get_db)):
    style = db.query(BusinessOwnerStyle).filter_by(id=id).first()
    if not style:
        raise HTTPException(status_code=404, detail="Tone example not found")

    style.scenario = data.scenario
    style.response = data.response
    db.commit()
    return {"message": "Tone example updated successfully"}

# 🗑️ 5. Delete a tone example
@router.delete("/sms-style/{id}")
def delete_owner_style(id: int, db: Session = Depends(get_db)):
    style = db.query(BusinessOwnerStyle).filter_by(id=id).first()
    if not style:
        raise HTTPException(status_code=404, detail="Tone example not found")

    db.delete(style)
    db.commit()
    return {"message": "Tone example deleted"}
