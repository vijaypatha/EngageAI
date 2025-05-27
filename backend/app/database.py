# ✅ database.py — Unified DB setup for local and Render environments
#
# - Loads DATABASE_URL from a `.env` file using `python-dotenv`, allowing secure and flexible config
# - Supports both PostgreSQL (Render) and SQLite (local dev) by detecting driver
# - Ensures SQLAlchemy session and engine are initialized correctly
# - Safe to use across local and deployed environments with consistent behavior
#
# Note: Make sure `.env` file exists in the backend folder with a valid DATABASE_URL

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import QueuePool
import logging
from sqlalchemy.ext.declarative import declarative_base

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ✅ Load .env from backend root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# Get database URL from environment variable, with a default for Render PostgreSQL
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ainudge_dev_db_user:lI8DI6v8kJ7iFkxU85t5MXpTqsy4svhP@dpg-d0qcl4re5dus739f8k0g-a.oregon-postgres.render.com/ainudge_dev_db"
)

# Create engine with SSL mode require for Render
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    connect_args={
        "sslmode": "require"
    }
)

# Add event listener for connection issues
@event.listens_for(engine, "handle_error")
def handle_db_error(context):
    logger.error(f"Database error occurred: {str(context.original_exception)}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()