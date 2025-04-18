from fastapi import APIRouter
from pydantic import BaseModel
from app.services.onboarding_preview import generate_onboarding_preview

router = APIRouter()

class PreviewRequest(BaseModel):
    business_name: str
    business_goal: str
    industry: str = ""
    customer_name: str = "there"

@router.post("/preview-message")
def onboarding_preview(req: PreviewRequest):
    preview = generate_onboarding_preview(
        business_name=req.business_name,
        business_goal=req.business_goal,
        industry=req.industry,
        customer_name=req.customer_name
    )
    return {"preview": preview}
