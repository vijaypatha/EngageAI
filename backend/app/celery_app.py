import os
from celery import Celery

# Explicit SSL settings for rediss:// (Upstash)
broker_use_ssl = {
    "ssl_cert_reqs": "CERT_REQUIRED",  # Use "CERT_NONE" only if testing with insecure SSL
}

# Read broker and result backend from environment
redis_url = os.getenv("REDIS_URL")

celery_app = Celery(
    "engageai_tasks",
    broker=redis_url,
    backend=redis_url,
)

celery_app.conf.broker_use_ssl = broker_use_ssl
celery_app.conf.result_backend_transport_options = broker_use_ssl

# Optional: You can explicitly name the task modules if needed, e.g.
# celery_app.autodiscover_tasks(['tasks', 'some_other_module'])

# Debug: You can include a basic task here if you want to test Celery
@celery_app.task
def ping():
    return "pong"