# backend/run_migrations.py (FINAL VERSION with .env loading)
import os
from alembic.config import Config
from alembic import command
from dotenv import load_dotenv # ADD THIS LINE

print("--- Starting database migration script ---")

# LOAD .ENV FILE FIRST
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    print(f".env file loaded from: {dotenv_path}")
else:
    print(f".env file not found at: {dotenv_path}. Relying on environment variables directly.")


database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise ValueError("FATAL: DATABASE_URL environment variable is not set. Please set it in your .env file or environment.")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

project_dir = os.path.dirname(os.path.abspath(__file__))
alembic_ini_path = os.path.join(project_dir, 'alembic.ini')
alembic_cfg = Config(alembic_ini_path)
alembic_cfg.set_main_option('sqlalchemy.url', database_url)

print(f"--- Running migrations for database: {alembic_cfg.get_main_option('sqlalchemy.url')} ---")
command.upgrade(alembic_cfg, "head")
print("--- Database migrations complete ---")