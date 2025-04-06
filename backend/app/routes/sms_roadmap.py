# ✨ What’s Powerful About It
# ✅ Auto-fetches customer + business info
# ✅ Injects owner tone style
# ✅ Prevents LLM cost duplication by checking if roadmap exists
# ✅ Stores all messages in DB in one step
# ✅ Returns structured roadmap for frontend

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Customer, BusinessProfile, RoadmapMessage
from app.services.sms_businessowner_style import get_owner_style_samples
from app.services.sms_customer_roadmap import generate_sms_roadmap
from app.services.sms_roadmap_parser import save_roadmap_messages
import json
import traceback
from pydantic import BaseModel

router = APIRouter()

class RoadmapRequest(BaseModel):
    customer_id: int
    force_regenerate: Optional[bool] = False

@router.post("/roadmap")
def generate_or_return_roadmap(
    payload: RoadmapRequest,
    db: Session = Depends(get_db)
):
    customer_id = payload.customer_id
    force = payload.force_regenerate

    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    business = db.query(BusinessProfile).filter(BusinessProfile.id == customer.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    tone_examples = get_owner_style_samples(business.id, db)

    existing_roadmap = db.query(RoadmapMessage).filter(
        RoadmapMessage.customer_id == customer_id
    ).all()

    if existing_roadmap and not force:
        return {
            "customer_id": customer_id,
            "roadmap": [
                {
                    "SMS Number": f"SMS {i+1}",
                    "smsContent": sms.sms_content,
                    "smsTiming": sms.send_time.strftime("Day %d, %I:%M %p") if sms.send_time else "",
                    "relevance": sms.relevance or "(from AI)",
                    "successIndicator": sms.success_indicator or "(from AI)",
                    "whatif_customer_does_not_respond": sms.no_response_plan or "(from AI)"
                }
                for i, sms in enumerate(existing_roadmap)
            ],
            "message": "AI roadmap already exists. Skipped regeneration."
        }

    if customer.is_generating_roadmap:
        raise HTTPException(
            status_code=409,
            detail="Roadmap generation already in progress for this customer."
        )

    customer.is_generating_roadmap = True
    db.commit()

    try:
        if existing_roadmap and force:
            for sms in existing_roadmap:
                if sms.status != "sent":
                    db.delete(sms)
            db.commit()

        roadmap = generate_sms_roadmap(
            business_type=business.industry,
            customer_name=customer.customer_name,
            lifecycle_stage=customer.lifecycle_stage,
            pain_points=customer.pain_points,
            interaction_history=customer.interaction_history,
            tone_examples=tone_examples,
            representative_name=business.representative_name,
        )

        if not roadmap or not roadmap.strip():
            raise HTTPException(status_code=500, detail="LLM returned empty roadmap.")
        
        owner_signature = f"{business.representative_name}, {business.business_name}".strip(", ")
        cleaned_roadmap = roadmap.strip() \
            .replace("Your Name", owner_signature) \
            .replace("Your Business", business.business_name)
      

        if cleaned_roadmap.startswith("```json"):
            cleaned_roadmap = cleaned_roadmap.removeprefix("```json").strip()
        if cleaned_roadmap.startswith("```"):
            cleaned_roadmap = cleaned_roadmap.removeprefix("```").strip()
        if cleaned_roadmap.endswith("```"):
            cleaned_roadmap = cleaned_roadmap.removesuffix("```").strip()

        parsed_roadmap = json.loads(cleaned_roadmap)
        save_roadmap_messages(cleaned_roadmap, customer, db)

    except HTTPException as e:
        raise e
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Unhandled roadmap error: {str(e)}")

    finally:
        customer.is_generating_roadmap = False
        db.commit()

    return {
            "customer_id": customer.id,
            "roadmap": parsed_roadmap,
            "message": "New roadmap generated and saved."
        }
