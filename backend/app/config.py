from pydantic_settings import BaseSettings
from functools import lru_cache
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    # App settings
    APP_NAME: str = "AI SMS Scheduler"
    DEBUG: bool = True
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")

    # Database settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://localhost/engage_ai")

    # Redis settings
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_BACKEND_URL: str = os.getenv("CELERY_BACKEND_URL", "redis://localhost:6379/0")

    # Twilio settings
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")
    TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")
    TWILIO_SID: str = os.getenv("TWILIO_SID", "")
    TWILIO_DEFAULT_MESSAGING_SERVICE_SID: str = os.getenv("TWILIO_DEFAULT_MESSAGING_SERVICE_SID", "")
    TWILIO_SUPPORT_MESSAGING_SERVICE_SID: str = os.getenv("TWILIO_SUPPORT_MESSAGING_SERVICE_SID", "")
    print("🧪 Loaded TWILIO_DEFAULT_MESSAGING_SERVICE_SID:", TWILIO_DEFAULT_MESSAGING_SERVICE_SID)

    # OpenAI settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # JWT settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-jwt-secret-key-here")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    FRONTEND_APP_URL: str = os.getenv("FRONTEND_APP_URL", "http://localhost:3000") # Add/Confirm this


    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from environment

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()

settings = get_settings()
