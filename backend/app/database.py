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
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import logging

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO) 

# ✅ Load .env from backend root
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    logger.info(f".env file loaded from: {dotenv_path}")
else:
    logger.info(f".env file not found at: {dotenv_path}. Relying on environment variables directly.")


DEFAULT_DEV_DB_URL = "postgresql://ainudge_dev_db_user:lI8DI6v8kJ7iFkxU85t5MXpTqsy4svhP@dpg-d0qcl4re5dus739f8k0g-a.oregon-postgres.render.com/ainudge_dev_db"
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DEV_DB_URL)

if SQLALCHEMY_DATABASE_URL == DEFAULT_DEV_DB_URL and "RENDER" in os.environ: # Be more specific for Render
    logger.warning(f"DATABASE_URL environment variable not set on Render or matches default; using default DEV database: {DEFAULT_DEV_DB_URL}. Ensure this is intended for this environment.")
elif SQLALCHEMY_DATABASE_URL == DEFAULT_DEV_DB_URL:
    logger.info(f"Using default DEV database (DATABASE_URL env var not set or matches default): {DEFAULT_DEV_DB_URL}")
else:
    logger.info(f"Using DATABASE_URL from environment.") # Avoid logging the full URL in production if it contains sensitive info, or mask credentials. For now, this is fine for debugging.


# --- FIX: Added pool_pre_ping and pool_recycle for connection stability ---
engine_args = {
    "pool_size": 5,
    "max_overflow": 10,
    "pool_timeout": 30,
    "pool_recycle": 1800, # Recycle connections every 30 minutes
    "pool_pre_ping": True, # Check if connection is alive before use
}

if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
    engine_args["connect_args"] = {"sslmode": "require"}
    logger.info("SSL mode 'require' will be used for PostgreSQL engine.")
elif SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgres://"): # Render internal DSN often starts with postgres://
     # For Render internal DSNs, sslmode might not be needed or might be 'prefer'.
     # Render's documentation should clarify. For now, assuming explicit external DSNs.
     # If your internal DSN doesn't need explicit sslmode, you might adjust this.
    engine_args["connect_args"] = {"sslmode": "prefer"} # Example for internal, adjust as per Render docs
    logger.info("SSL mode 'prefer' (example for internal DSN) will be used for PostgreSQL engine.")


engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_args)

# Valid event listener for general database errors
@event.listens_for(engine, "handle_error")
def handle_db_error(context):
    logger.error(
        (
            f"Database error occurred. Statement: {str(context.statement)} "
            f"Parameters: {str(context.parameters)} "
            f"Exception: {str(context.original_exception)}"
        ),
        exc_info=context.original_exception # Provides full traceback for the original error
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

logger.info("Database engine and session configured.")
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    logger.info("Connected to SQLite database.")
elif "connect_args" in engine_args and "sslmode" in engine_args["connect_args"]:
    logger.info(f"PostgreSQL engine configured with SSL mode: {engine_args['connect_args']['sslmode']}")
else:
    logger.info("PostgreSQL engine configured (no explicit SSL connect_args - check URL if needed or if using internal DSN).")