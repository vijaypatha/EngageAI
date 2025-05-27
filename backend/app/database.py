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
# from sqlalchemy.orm import declarative_base # This is equivalent to sqlalchemy.ext.declarative.declarative_base
from sqlalchemy.ext.declarative import declarative_base # Explicit import
# from sqlalchemy.engine.url import make_url # Not used in the current setup
# from sqlalchemy.pool import QueuePool # Not explicitly used, create_engine handles default pooling
import logging

# Configure logger
logger = logging.getLogger(__name__)
# BasicConfig should ideally be called once at the application entry point.
# If called multiple times or after loggers are retrieved, it might not behave as expected.
# Assuming it's called early enough here or managed at a higher level.
logging.basicConfig(level=logging.INFO) 

# ✅ Load .env from backend root
# Assumes .env is in the parent directory of the directory containing this database.py file
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    logger.info(f".env file loaded from: {dotenv_path}")
else:
    logger.info(f".env file not found at: {dotenv_path}. Relying on environment variables directly.")


# Get database URL from environment variable, with a default for Render PostgreSQL (DEV DB)
# This default means if DATABASE_URL is not set in the environment, it will use the dev DB.
# Ensure your production Celery worker environment has DATABASE_URL set to your PROD DB.
DEFAULT_DEV_DB_URL = "postgresql://ainudge_dev_db_user:lI8DI6v8kJ7iFkxU85t5MXpTqsy4svhP@dpg-d0qcl4re5dus739f8k0g-a.oregon-postgres.render.com/ainudge_dev_db"
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DEV_DB_URL)

if SQLALCHEMY_DATABASE_URL == DEFAULT_DEV_DB_URL:
    logger.warning(f"DATABASE_URL environment variable not set or matches default; using default DEV database: {DEFAULT_DEV_DB_URL}")
else:
    logger.info(f"Using DATABASE_URL from environment: {SQLALCHEMY_DATABASE_URL}")


# Create engine with SSL mode require for Render and pool_pre_ping
engine_args = {
    "pool_size": 5,
    "max_overflow": 10,
    "pool_timeout": 30,  # seconds
    "pool_recycle": 1800, # seconds (30 minutes)
    "pool_pre_ping": True, # ✅ ADDED THIS LINE
}

# For PostgreSQL, include SSL arguments
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
    engine_args["connect_args"] = {"sslmode": "require"}
    logger.info("SSL mode 'require' enabled for PostgreSQL engine.")
elif SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgres"): # Render internal might start with postgres://
    # For Render internal DSNs, sslmode might not be needed or might be 'prefer'
    # Render's documentation should clarify. For now, assuming explicit external DSNs.
    # If your internal DSN doesn't need explicit sslmode, you might adjust this.
    engine_args["connect_args"] = {"sslmode": "prefer"} # Example for internal, adjust as per Render docs
    logger.info("SSL mode 'prefer' (example for internal DSN) enabled for PostgreSQL engine.")


engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_args)

# Add event listener for connection issues (optional, but good for debugging)
@event.listens_for(engine, "checkout_fail")
def checkout_fail(dbapi_connection, connection_record, exception):
    logger.error(f"Connection checkout failed: {exception}", exc_info=True)

@event.listens_for(engine, "handle_error")
def handle_db_error(context):
    # This logs the original exception, which is good.
    # The context object has more details: context.connection, context.statement, context.parameters
    logger.error(f"Database error occurred during operation. Exception: {str(context.original_exception)}", exc_info=context.original_exception)
    # If context.connection is not None and not context.connection.closed:
    # logger.error(f"Connection info: {context.connection.info}")


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
elif "connect_args" in engine_args:
    logger.info(f"PostgreSQL engine configured with connect_args: {engine_args['connect_args']}")
else:
    logger.info("PostgreSQL engine configured (no explicit SSL connect_args - check URL if SSL is needed).")

