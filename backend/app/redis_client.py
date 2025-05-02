import redis
from app.config import settings
import logging

logger = logging.getLogger(__name__)

try:
    redis_client = redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_timeout=5
    )
    # Test the connection
    redis_client.ping()
    logger.info("✅ Redis connection established")
except redis.ConnectionError as e:
    logger.error(f"❌ Could not connect to Redis: {str(e)}")
    redis_client = None
except Exception as e:
    logger.error(f"❌ Unexpected error connecting to Redis: {str(e)}")
    redis_client = None 