# ✅ database.py — Unified DB setup for local and Render environments
# ... (keep existing comments and initial imports) ...

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker # declarative_base is imported below
# Add async imports
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base # This is already here, good.
import logging
from typing import AsyncGenerator
from urllib.parse import urlparse

# Configure logger (keep existing)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ✅ Load .env from backend root (keep existing)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# Get database URL from environment variable (keep existing)
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://engageai_db_user:THtPfaorNWqMDB5grrU6VRwuijSzErZe@dpg-cvqo321r0fns73a3722g-a.oregon-postgres.render.com/engageai_db"
)

# --- Synchronous Engine Setup (Keep existing) ---
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    connect_args={
        "sslmode": "require"
    } if SQLALCHEMY_DATABASE_URL and "render.com" in SQLALCHEMY_DATABASE_URL else {} # Conditional SSL for Render
)

# Add event listener for connection issues (Keep existing)
@event.listens_for(engine, "handle_error")
def handle_db_error(context):
    logger.error(f"Database error occurred: {str(context.original_exception)}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base() # This Base can be used by both sync and async models if they share structure

def get_db(): # Your existing synchronous session provider (Keep existing)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Asynchronous Engine and Session Setup ---
if SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    # Parse the URL to get connection parameters
    parsed = urlparse(SQLALCHEMY_DATABASE_URL)
    user = parsed.username
    password = parsed.password
    host = parsed.hostname
    port = parsed.port or 5432
    database = parsed.path[1:]  # Remove leading slash
    
    # Construct the async URL with explicit parameters
    ASYNC_SQLALCHEMY_DATABASE_URL = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
else:
    logger.warning(
        f"Could not automatically derive async database URL from: {SQLALCHEMY_DATABASE_URL}. "
        "Ensure ASYNC_SQLALCHEMY_DATABASE_URL is correctly configured if not using PostgreSQL."
    )
    ASYNC_SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL

logger.info("Creating async engine...")
async_engine = create_async_engine(
    ASYNC_SQLALCHEMY_DATABASE_URL,
    future=True,
    connect_args={
        "ssl": "require"
    } if "render.com" in ASYNC_SQLALCHEMY_DATABASE_URL else {}
)
logger.info("Async engine created successfully")

AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get an async database session.
    Ensures the session is closed after the request.
    """
    async_session_instance = AsyncSessionLocal()
    try:
        yield async_session_instance
    except Exception:
        await async_session_instance.rollback()
        raise
    finally:
        await async_session_instance.close()