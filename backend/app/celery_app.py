from celery import Celery
from dotenv import load_dotenv
import os

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

# Add SSL options for rediss://
broker_use_ssl = {}
backend_use_ssl = {}

if REDIS_URL and REDIS_URL.startswith("rediss://"):
    broker_use_ssl = {"ssl_cert_reqs": "CERT_NONE"}
    backend_use_ssl = {"ssl_cert_reqs": "CERT_NONE"}

celery_app = Celery(
    "engageai_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.broker_use_ssl = broker_use_ssl
celery_app.conf.redis_backend_use_ssl = backend_use_ssl

celery_app.conf.enable_utc = True
celery_app.conf.timezone = "UTC"
