# backend/app/main.py
# Main entry point for the AI SMS Scheduler application
# Provides businesses with an intelligent SMS platform for customer engagement and automated communications
from datetime import datetime
import logging
from typing import Dict, Optional
import os 

from fastapi import FastAPI, HTTPException, Request, APIRouter
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.middleware.sessions import SessionMiddleware

from app.celery_app import ping
from app.config import settings
from app.database import Base, engine
from app.models import (
    BusinessProfile,
    ConsentLog,
    Customer,
    ScheduledSMS,
)
from app.routes import (
    ai_routes,
    business_routes,
    consent_routes,
    conversation_routes,
    customer_routes,
    engagement_routes,
    engagement_workflow_routes,
    message_routes,
    message_workflow_routes,
    roadmap_routes,
    roadmap_workflow_routes,
    style_routes,
    twilio_routes,
    twilio_webhook,
    onboarding_preview_route,
    auth_routes,
    review,
    instant_nudge_routes,
    copilot_nudge_routes,
    targeted_event_routes,
    tag_routes,
    follow_up_plan_routes,
    copilot_growth_routes
)
from app.schemas import (
    BusinessProfileCreate,
    ConsentLogCreate,
    CustomerCreate,
    ScheduledSMSCreate,
)

# Configure logging
logger = logging.getLogger(__name__)

# Initialize FastAPI app with configuration
app = FastAPI(
    title="AI SMS Scheduler",
    description="API for scheduling and sending AI-powered SMS messages",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://engage-ai-seven.vercel.app",
        "https://www.engage-ai-seven.vercel.app",
        "https://nudge-ai-seven.vercel.app",
        "https://ainudge.app",
        "https://www.ainudge.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Initialize database
Base.metadata.create_all(bind=engine)

# Add session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    https_only=False,
    session_cookie="session",
    max_age=30 * 24 * 60 * 60

)

# --- Define a parent router for all API endpoints ---
api_router = APIRouter(prefix="/api")

# Register all child routers with the parent api_router
api_router.include_router(twilio_routes.router, prefix="/twilio", tags=["twilio"])
api_router.include_router(business_routes.router, prefix="/business-profile", tags=["business"])
api_router.include_router(customer_routes.router, prefix="/customers", tags=["customers"])
api_router.include_router(consent_routes.router, prefix="/consent", tags=["consent"])
api_router.include_router(style_routes.router, prefix="/sms-style", tags=["style"])
api_router.include_router(ai_routes.router, prefix="/ai", tags=["ai"])
api_router.include_router(roadmap_routes.router, prefix="/roadmap", tags=["roadmap"])
api_router.include_router(roadmap_workflow_routes.router, prefix="/roadmap-workflow", tags=["roadmap-workflow"])
api_router.include_router(conversation_routes.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(message_routes.router, prefix="/messages", tags=["messages"])
api_router.include_router(message_workflow_routes.router, prefix="/message-workflow", tags=["message-workflow"])
api_router.include_router(engagement_routes.router, prefix="/engagements", tags=["engagements"])
api_router.include_router(engagement_workflow_routes.router, prefix="/engagement-workflow", tags=["engagement-actions"])
api_router.include_router(onboarding_preview_route.router, prefix="/onboarding-preview", tags=["onboarding"])
api_router.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
api_router.include_router(review.router, prefix="/review", tags=["review"])
api_router.include_router(instant_nudge_routes.router, prefix="/instant-nudge", tags=["instant-nudge"])
api_router.include_router(copilot_nudge_routes.router, prefix="/ai-nudge-copilot", tags=["AI Nudge Co-Pilot"] )
api_router.include_router(targeted_event_routes.router, prefix="/targeted-events", tags=["Targeted Events"] )
api_router.include_router(follow_up_plan_routes.router, prefix="/follow-up-plans", tags=["Follow-up Nudge Plans"] )
api_router.include_router(tag_routes.router, prefix="/tags", tags=["Tags"])
api_router.include_router(copilot_growth_routes.router, prefix="/copilot-growth", tags=["AI Nudge Co-Pilot - Growth"])

# Include the main api_router in the app
app.include_router(api_router)

# --- Non-API routes (if any) can be included directly on the app ---
# This Twilio webhook is often kept outside the /api prefix
app.include_router(twilio_webhook.router, prefix="/twilio", tags=["twilio"])


@app.get("/", response_model=Dict[str, str])
async def read_root() -> Dict[str, str]:
    """Welcome endpoint for the API."""
    return {"message": "Welcome to the AI SMS Scheduler!"}

@app.get("/debug/redis-url", response_model=Dict[str, Optional[str]])
async def debug_redis_url() -> Dict[str, Optional[str]]:
    """Debug endpoint to check Redis URL configuration."""
    return {"REDIS_URL": os.getenv("REDIS_URL")}

@app.get("/debug-ping", response_model=Dict[str, str])
async def trigger_ping() -> Dict[str, str]:
    """Debug endpoint to test Celery task execution."""
    task = ping.delay()
    return {"task_id": task.id}

@app.get("/debug/celery-basic", response_model=Dict[str, str])
async def trigger_basic_task() -> Dict[str, str]:
    """Debug endpoint to verify basic functionality."""
    task = ping.delay()
    return {"ping_task_id": task.id}

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """Handle request validation errors."""
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )

@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# 🛣️ Log active routes for debugging
logger.info(f"🟢 TWILIO_DEFAULT_MESSAGING_SERVICE_SID: {settings.TWILIO_DEFAULT_MESSAGING_SERVICE_SID}")
for route in app.routes:
    if isinstance(route, APIRoute):
        logger.info(f"🔵  Active route: {route.path} [{','.join(route.methods)}]")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )