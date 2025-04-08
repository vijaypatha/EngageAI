from celery import Celery
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Use REDIS_URL for both broker and backend
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "engageai_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.enable_utc = True
celery_app.conf.timezone = "UTC"
