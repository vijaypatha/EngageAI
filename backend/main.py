from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # ✅ move up top
from app.routes import business, customers, review, engagement, twilio_webhook, auth
from app.database import engine, Base
from starlette.middleware.sessions import SessionMiddleware
from app.routes import sms_scheduling, sms_roadmap, message_status, sms_businessowner_style_endpoints, conversations




app = FastAPI(title="AI SMS Scheduler", version="1.0")

# ✅ CORS comes BEFORE routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000",
                   "https://engage-ai-seven.vercel.app",
                   "https://www.engage-ai-seven.vercel.app"
                   ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(twilio_webhook.router, prefix="/twilio", tags=["Twilio"])
# ✅ Enables reading/writing secure cookies (required for session logic)
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key",
    same_site="none",   # 👈 required for cross-site cookie
    https_only=True     # 👈 required if SameSite=none
)


# ✅ Now include routers
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





@app.get("/")
def read_root():
    return {"message": "Welcome to the AI SMS Scheduler!"}


# ✅ THEN route logger (last)

from fastapi.routing import APIRoute

print("\n📡 Active Routes:")
for route in app.routes:
    if isinstance(route, APIRoute):
        print(f"🔹 {route.path} [{','.join(route.methods)}]")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
