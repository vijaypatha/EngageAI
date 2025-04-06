
from celery import Celery
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize Celery app
celery_app = Celery(
    "engageai_tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
)

celery_app.conf.enable_utc = True
celery_app.conf.timezone = "UTC"
