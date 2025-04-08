import os
from celery import Celery
import ssl
from dotenv import load_dotenv 
load_dotenv()  

# Pull Redis URL from environment
redis_url = os.getenv("REDIS_URL")
print(f"📦 Loaded REDIS_URL: {redis_url}")  # ✅ TEMP DEBUG

# Define required SSL config
ssl_options = {
    "ssl_cert_reqs": ssl.CERT_REQUIRED,
}

# Create Celery app
celery_app = Celery(
    "engageai_tasks",
    broker=redis_url,
    backend=redis_url,
)

# Apply SSL options to broker and result backend
celery_app.conf.broker_use_ssl = ssl_options
celery_app.conf.redis_backend_use_ssl = ssl_options

# Optional test task (can be removed)
@celery_app.task
def ping():
    return "pong"