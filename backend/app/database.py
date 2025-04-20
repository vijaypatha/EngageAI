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
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import QueuePool
import logging

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ✅ Load .env from backend root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not found in .env or environment.")

Base = declarative_base()
url = make_url(DATABASE_URL)

# Configure engine with proper SSL for remote PostgreSQL
engine_args = {
    "poolclass": QueuePool,
    "pool_size": 5,
    "max_overflow": 10,
    "pool_timeout": 30,
    "pool_recycle": 1800,  # Recycle connections after 30 minutes
    "pool_pre_ping": True  # Enable connection health checks
}

if url.drivername.startswith('postgresql'):
    engine_args["connect_args"] = {
        "sslmode": "require",
        "connect_timeout": 10
    }

engine = create_engine(DATABASE_URL, **engine_args)

# Add event listener for connection issues
@event.listens_for(engine, "handle_error")
def handle_db_error(context):
    logger.error(f"Database error occurred: {str(context.original_exception)}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()