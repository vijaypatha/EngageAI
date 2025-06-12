# backend/app/main.py
import logging
from typing import Dict, Optional, Callable, Awaitable
import os

from fastapi import FastAPI, HTTPException, Request, APIRouter
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from app.celery_app import ping
from app.config import settings
from app.database import Base, engine
from app.models import BusinessProfile, ConsentLog, Customer, ScheduledSMS
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

# Initialize FastAPI app
app = FastAPI(
    title="AI SMS Scheduler",
    description="API for scheduling and sending AI-powered SMS messages",
    version="1.0.0",
)

# --- Middleware to strip the /api prefix if it exists ---
@app.middleware("http")
async def strip_api_prefix(request: Request, call_next):
    logger.info(f"[strip_api_prefix] Received request for original_url_path: {request.url.path}, current_scope_path: {request.scope.get('path')}")
    original_url_path = request.url.path # Unmodified URL path
    current_scope_path = request.scope.get('path', original_url_path) # Path that router will see, possibly modified by other middleware

    final_scope_path_for_router = current_scope_path # Assume no change initially

    if current_scope_path.startswith("/api"):
        new_path_segment = current_scope_path[4:] # Remove '/api'

        if not new_path_segment: # Original scope path was "/api" or "/api/"
            final_scope_path_for_router = "/"
        elif not new_path_segment.startswith("/"):
            final_scope_path_for_router = "/" + new_path_segment
        else:
            final_scope_path_for_router = new_path_segment

        request.scope['path'] = final_scope_path_for_router
        logger.info(f"[strip_api_prefix] Original URL path: {original_url_path}. Scope path before strip: {current_scope_path}. Stripped scope path for router to: {final_scope_path_for_router}")
    else:
        logger.info(f"[strip_api_prefix] Scope path {current_scope_path} (from URL path {original_url_path}) does not start with /api, no modification by this middleware.")

    response = await call_next(request)
    # Optional: log response status code here if needed
    # logger.info(f"[strip_api_prefix] Responding to {original_url_path}. Router saw {final_scope_path_for_router}. Status: {response.status_code}")
    return response

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

# --- Register route handlers without the /api prefix ---
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
app.include_router(instant_nudge_routes.router, prefix="/instant-nudge", tags=["instant-nudge"])
app.include_router(twilio_webhook.router, prefix="/twilio", tags=["twilio"]) # Note: This might be a duplicate if twilio_routes also has webhooks
app.include_router(copilot_nudge_routes.router, prefix="/ai-nudge-copilot", tags=["AI Nudge Co-Pilot"])
app.include_router(targeted_event_routes.router, prefix="/targeted-events", tags=["Targeted Events"])
app.include_router(follow_up_plan_routes.router, prefix="/follow-up-plans", tags=["Follow-up Nudge Plans"])
app.include_router(tag_routes.router, prefix="/tags", tags=["Tags"])
app.include_router(copilot_growth_routes.router, prefix="/copilot-growth", tags=["AI Nudge Co-Pilot - Growth"])

@app.get("/", response_model=Dict[str, str])
async def read_root() -> Dict[str, str]:
    return {"message": "Welcome to the AI SMS Scheduler!"}

# ... (rest of your debug routes and exception handlers remain the same) ...
@app.get("/debug/redis-url", response_model=Dict[str, Optional[str]])
async def debug_redis_url() -> Dict[str, Optional[str]]:
    return {"REDIS_URL": os.getenv("REDIS_URL")}
@app.get("/debug-ping", response_model=Dict[str, str])
async def trigger_ping() -> Dict[str, str]:
    task = ping.delay()
    return {"task_id": task.id}
@app.get("/debug/celery-basic", response_model=Dict[str, str])
async def trigger_basic_task() -> Dict[str, str]:
    task = ping.delay()
    return {"ping_task_id": task.id}
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})
@app.exception_handler(HTTPException)
async def custom_http_exception_logger_handler(request: Request, exc: HTTPException):
    # Ensure logger is available (it's global in main.py)
    # import logging
    # logger = logging.getLogger(__name__) # Redundant if logger is truly global and already set up

    log_message_prefix = f"[CustomHTTPExceptionHandler] Path: {request.method} {request.url.path}"

    if exc.status_code == 404:
        logger.warning(f"{log_message_prefix} - Result: 404 Not Found. Detail: {exc.detail}")
        # For 404s, it's often useful to see headers to debug proxy issues, content negotiation, etc.
        logger.debug(f"{log_message_prefix} - Request Headers for 404: {{dict(request.headers)}}")
    else:
        # Log other HTTPExceptions as errors, as they might indicate server-side issues
        # or bad client requests that are not just 'not found'.
        logger.error(f"{log_message_prefix} - Result: HTTPException Status={exc.status_code}, Detail: {exc.detail}")
        logger.debug(f"{log_message_prefix} - Request Headers: {{dict(request.headers)}}")

    # Return a JSON response consistent with FastAPI's default for HTTPExceptions
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail if exc.detail is not None else "An HTTP error occurred."}, # Ensure detail is not None
        headers=getattr(exc, "headers", None) # Preserve headers from original exception if any
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# 🛣️ Log active routes for debugging
logger.info(f"🟢 TWILIO_DEFAULT_MESSAGING_SERVICE_SID: {settings.TWILIO_DEFAULT_MESSAGING_SERVICE_SID}")
for route in app.routes:
    if isinstance(route, APIRoute):
        logger.info(f"🔵  Active route: {route.path} [{','.join(route.methods)}]")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)