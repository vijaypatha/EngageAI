# File: backend/app/celery_app.py

import os
from dotenv import load_dotenv
import logging
from celery import Celery
import ssl
# Removed unused SessionLocal import if not needed directly in this file
# from app.database import SessionLocal

# Add logger definition:
logger = logging.getLogger(__name__)

# ✅ Load .env file (required for local and Render environments)
load_dotenv()

# ✅ Read Redis URL from environment
redis_url = os.getenv("REDIS_URL")
print(f"📦 Loaded REDIS_URL: {redis_url}")  # TEMP: confirm it's loading

# ✅ Define Redis SSL options (only needed for rediss://)
ssl_options = {
    "ssl_cert_reqs": ssl.CERT_NONE  # Use CERT_REQUIRED if you upload certs
}

# --- Define broker transport options (Includes keepalives) ---
broker_transport_options = {
    'visibility_timeout': 3600, # Default visibility timeout
    'socket_timeout': 10,       # Socket read/write timeout
    'socket_connect_timeout': 10, # Socket connect timeout
    'socket_keepalive': True,     # <<< Enable TCP keepalives
    # Optional: Adjust keepalive settings if needed (values in seconds)
    # 'socket_keepalive_options': {
    #     'TCP_KEEPIDLE': 60,
    #     'TCP_KEEPINTVL': 10,
    #     'TCP_KEEPCNT': 6
    # }
}

# ✅ Create Celery app AND include transport options
celery_app = Celery(
    "engageai_tasks",
    broker=redis_url,
    backend=redis_url,
    broker_transport_options=broker_transport_options # Pass options here
    # Optional: Apply to backend too if needed for results
    # backend_transport_options=broker_transport_options
)

# --- Conditionally Apply SSL Options based on URL scheme ---
# Check if redis_url is not None before calling startswith
if redis_url and redis_url.startswith("rediss://"):
    print("🔒 Applying SSL options for rediss:// connection")
    celery_app.conf.broker_use_ssl = ssl_options
    celery_app.conf.redis_backend_use_ssl = ssl_options
else:
    print("🚫 Skipping SSL options for non-rediss:// connection (e.g., localhost)")
# --- End Conditional Apply ---

# --- Configure Timezone Settings ---
celery_app.conf.enable_utc = True
celery_app.conf.timezone = 'UTC'
# --- End Timezone Config ---

# ✅ Optional ping task (Example)
@celery_app.task(name="ping")
def ping():
    print("🏓 PING TASK EXECUTED")
    logger.info("🏓 PING TASK EXECUTED - IN LOGS")
    return "pong"

# Discover tasks from app.celery_tasks module
celery_app.autodiscover_tasks(['app.celery_tasks'])
print("✅ Celery is configured and tasks are being discovered from app.celery_tasks")