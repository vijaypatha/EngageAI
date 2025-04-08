import os
from dotenv import load_dotenv
from celery import Celery
import ssl
from app.database import SessionLocal  # ensures Celery uses Postgres

# ✅ Load .env file (required for local and Render environments)
load_dotenv()

# ✅ Read Redis URL from environment
redis_url = os.getenv("REDIS_URL")
print(f"📦 Loaded REDIS_URL: {redis_url}")  # TEMP: confirm it's loading

# ✅ Set Redis SSL options
ssl_options = {
    "ssl_cert_reqs": ssl.CERT_NONE  # Use CERT_REQUIRED if you upload certs
}

# ✅ Create Celery app
celery_app = Celery(
    "engageai_tasks",
    broker=redis_url,
    backend=redis_url,
)

# ✅ Apply SSL options to broker + backend
celery_app.conf.broker_use_ssl = ssl_options
celery_app.conf.redis_backend_use_ssl = ssl_options

# ✅ Optional ping task
@celery_app.task(name = "ping")
def ping():
    return "pong"

celery_app.autodiscover_tasks(['app.celery_tasks'])
print("✅ Celery is configured and tasks are being discovered from app.celery_tasks")