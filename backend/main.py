# backend/main.py
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
from app.routes import (
    ai_routes,
    business_routes,
    composer_routes, 
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

logger = logging.getLogger(__name__)
app = FastAPI(
    title="AI SMS Scheduler",
    description="API for scheduling and sending AI-powered SMS messages",
    version="1.0.0",
)

# --- Middleware Configuration ---
@app.middleware("http")
async def strip_api_prefix(request: Request, call_next):
    path_to_evaluate = request.scope.get('path') or request.url.path
    if path_to_evaluate.startswith("/api"):
        new_path_segment = path_to_evaluate[4:]
        final_scope_path_for_router = "/" if not new_path_segment else ("/" + new_path_segment if not new_path_segment.startswith("/") else new_path_segment)
        request.scope['path'] = final_scope_path_for_router
    response = await call_next(request)
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://ainudge.app",
        "https://www.ainudge.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="none",
    https_only=True,
    session_cookie="session",
    max_age=30 * 24 * 60 * 60
)


# --- API Routers ---
app.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
app.include_router(business_routes.router, prefix="/business-profile", tags=["business"])
app.include_router(composer_routes.router, prefix="/composer", tags=["composer"]) 
app.include_router(customer_routes.router, prefix="/customers", tags=["customers"])
app.include_router(tag_routes.router, prefix="/tags", tags=["Tags"])
app.include_router(review.router, prefix="/review", tags=["review"])
app.include_router(instant_nudge_routes.router, prefix="/instant-nudge", tags=["instant-nudge"])
app.include_router(conversation_routes.router, prefix="/conversations", tags=["conversations"])
app.include_router(engagement_workflow_routes.router, prefix="/engagement-workflow", tags=["engagement-actions"])
app.include_router(ai_routes.router, prefix="/ai", tags=["ai"])
app.include_router(copilot_nudge_routes.router, prefix="/ai-nudge-copilot", tags=["AI Nudge Co-Pilot"])
app.include_router(copilot_growth_routes.router, prefix="/copilot-growth", tags=["AI Nudge Co-Pilot - Growth"])
app.include_router(targeted_event_routes.router, prefix="/targeted-events", tags=["Targeted Events"])
app.include_router(follow_up_plan_routes.router, prefix="/follow-up-plans", tags=["Follow-up Nudge Plans"])
app.include_router(twilio_routes.router, prefix="/twilio", tags=["twilio"])
app.include_router(twilio_webhook.router, prefix="/twilio", tags=["twilio"])

# Deprecated or internal-use routes below
app.include_router(consent_routes.router, prefix="/consent", tags=["consent"])
app.include_router(style_routes.router, prefix="/sms-style", tags=["style"])
app.include_router(roadmap_routes.router, prefix="/roadmap", tags=["roadmap"])
app.include_router(roadmap_workflow_routes.router, prefix="/roadmap-workflow", tags=["roadmap-workflow"])
app.include_router(message_routes.router, prefix="/messages", tags=["messages"])
app.include_router(message_workflow_routes.router, prefix="/message-workflow", tags=["message-workflow"])
app.include_router(engagement_routes.router, prefix="/engagements", tags=["engagements"])
app.include_router(onboarding_preview_route.router, prefix="/onboarding-preview", tags=["onboarding"])


# --- Root and Debug Endpoints ---
@app.get("/", response_model=Dict[str, str])
async def read_root() -> Dict[str, str]:
    return {"message": "Welcome to the AI SMS Scheduler!"}

@app.get("/debug/celery-ping", response_model=Dict[str, str])
async def trigger_ping() -> Dict[str, str]:
    task = ping.delay()
    return {"ping_task_id": task.id}

# --- Exception Handlers ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.error(f"[RequestValidationError] Path: {request.method} {request.url.path} - Detail: {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

@app.exception_handler(HTTPException)
async def custom_http_exception_logger_handler(request: Request, exc: HTTPException):
    logger.error(f"[HTTPException] Path: {request.method} {request.url.path} - Result: {exc.status_code}, Detail: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail if exc.detail is not None else "An HTTP error occurred."},
        headers=getattr(exc, "headers", None)
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"[Unhandled Exception] Path: {request.method} {request.url.path} - Exception: {str(exc)}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "An internal server error occurred."})