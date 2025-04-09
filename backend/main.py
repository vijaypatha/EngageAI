from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import business, customers, review, engagement, twilio_webhook, auth
from app.database import engine, Base
from starlette.middleware.sessions import SessionMiddleware
from app.routes import sms_scheduling, sms_roadmap, message_status, sms_businessowner_style_endpoints, conversations

from app.celery_app import ping  # ✅ import ping early
import os
print("🔍 REDIS_URL loaded in main.py:", os.getenv("REDIS_URL"))


app = FastAPI(title="AI SMS Scheduler", version="1.0")

# ✅ CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://engage-ai-seven.vercel.app",
        "https://www.engage-ai-seven.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ DB Init
Base.metadata.create_all(bind=engine)

# ✅ Session Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key",
    same_site="none",
    https_only=True,
    session_cookie="session"
)

# ✅ Routers
app.include_router(twilio_webhook.router, prefix="/twilio", tags=["Twilio"])
app.include_router(business.router, prefix="/business-profile", tags=["Business Profile"])
app.include_router(customers.router, prefix="/customers", tags=["Customers"])
app.include_router(sms_roadmap.router, prefix="/ai_sms", tags=["AI SMS"])
app.include_router(sms_scheduling.router, prefix="/sms", tags=["SMS Scheduling"])
app.include_router(review.router, prefix="/review", tags=["SMS Review"])
app.include_router(engagement.router, prefix="/engagement", tags=["Engagement Tracking"])
app.include_router(message_status.router)
app.include_router(sms_businessowner_style_endpoints.router)
app.include_router(conversations.router)
app.include_router(auth.router)

# ✅ Root
@app.get("/")
def read_root():
    return {"message": "Welcome to the AI SMS Scheduler!"}

# ✅ Debug route: check REDIS_URL
@app.get("/debug/redis-url")
def debug_redis_url():
    import os
    return {"REDIS_URL": os.getenv("REDIS_URL")}

# ✅ Debug route: trigger ping task
@app.get("/debug-ping")
def trigger_ping():
    task = ping.delay()
    return {"task_id": task.id}

# ✅ Debug route: trigger a real SMS task immediately
@app.get("/test-sms")
def test_sms_now():
    from app.celery_tasks import schedule_sms_task
    print("🚀 [FASTAPI] Dispatching Celery task for scheduled_sms_id=2")
    schedule_sms_task.apply_async(args=[2])  # Use scheduled_sms ID 2
    return {"status": "SMS task dispatched"}

# ✅ Debug route: verify basic Celery task dispatch
@app.get("/debug/celery-basic")
def trigger_basic_task():
    from app.celery_app import ping
    task = ping.delay()
    return {"ping_task_id": task.id}

# ✅ Print active routes
from fastapi.routing import APIRoute
print("\n📡 Active Routes:")
for route in app.routes:
    if isinstance(route, APIRoute):
        print(f"🔹 {route.path} [{','.join(route.methods)}]")

# ✅ Main entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)