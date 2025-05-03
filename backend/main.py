# Main entry point for the AI SMS Scheduler application
# Provides businesses with an intelligent SMS platform for customer engagement and automated communications
from datetime import datetime
import logging
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Request
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
    instant_nudge_routes
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
    session_cookie="session"
)

# Register route handlers
app.include_router(twilio_routes.router, prefix="/twilio", tags=["twilio"])
app.include_router(business_routes.router, prefix="/business-profile", tags=["business"])
app.include_router(customer_routes.router, prefix="/customers", tags=["customers"])
app.include_router(consent_routes.router, prefix="/consent", tags=["consent"])
app.include_router(style_routes.router, prefix="/sms-style", tags=["style"])
app.include_router(ai_routes.router, prefix="/ai", tags=["ai"])
app.include_router(roadmap_routes.router, prefix="/roadmap", tags=["roadmap"])
app.include_router(roadmap_workflow_routes.router, prefix="/roadmap-workflow", tags=["roadmap-workflow"])
app.include_router(conversation_routes.router, prefix="/conversations", tags=["conversations"])
app.include_router(message_routes.router, prefix="/messages", tags=["messages"])
app.include_router(message_workflow_routes.router, prefix="/message-workflow", tags=["message-workflow"])
app.include_router(engagement_routes.router, prefix="/engagements", tags=["engagements"])
app.include_router(engagement_workflow_routes.router, prefix="/engagement-workflow", tags=["engagement-actions"])
app.include_router(onboarding_preview_route.router, prefix="/onboarding-preview", tags=["onboarding"])
app.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
app.include_router(review.router, prefix="/review", tags=["review"])
app.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
app.include_router(instant_nudge_routes.router, prefix="/instant-nudge", tags=["instant-nudge"])
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

@app.get("/test-sms", response_model=Dict[str, str])
async def test_sms_now() -> Dict[str, str]:
    """Debug endpoint to test SMS scheduling."""
    logger.info("Dispatching Celery task for scheduled_sms_id=2")
    schedule_sms_task.apply_async(args=[2])
    return {"status": "SMS task dispatched"}

@app.get("/debug/celery-basic", response_model=Dict[str, str])
async def trigger_basic_task() -> Dict[str, str]:
    """Debug endpoint to verify basic Celery functionality."""
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