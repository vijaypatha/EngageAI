import os
import ssl
from dotenv import load_dotenv
from celery import Celery

# Load env variables
load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Proper SSL config using ssl module
broker_use_ssl = None
backend_use_ssl = None

if REDIS_URL.startswith("rediss://"):
    broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}
    backend_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}

celery_app = Celery(
    "engageai_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Apply SSL config if needed
if broker_use_ssl:
    celery_app.conf.broker_use_ssl = broker_use_ssl
if backend_use_ssl:
    celery_app.conf.redis_backend_use_ssl = backend_use_ssl

celery_app.conf.enable_utc = True
celery_app.conf.timezone = "UTC"
