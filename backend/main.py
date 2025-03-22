from fastapi import FastAPI
from app.routes import business, customers, review, engagement
from app.database import engine, Base
from app.routes import sms_scheduling
from app.routes import sms_roadmap

app = FastAPI(title="AI SMS Scheduler", version="1.0")

Base.metadata.create_all(bind=engine)

app.include_router(business.router, prefix="/business-profile", tags=["Business Profile"])
app.include_router(customers.router, prefix="/customers", tags=["Customers"])
app.include_router(sms_roadmap.router, prefix="/ai_sms", tags=["AI SMS"])
app.include_router(sms_scheduling.router, prefix="/sms", tags=["SMS Scheduling"])
app.include_router(review.router, prefix="/review", tags=["SMS Review"])
app.include_router(engagement.router, prefix="/engagement", tags=["Engagement Tracking"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the AI SMS Scheduler!"}
