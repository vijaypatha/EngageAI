# backend/run_migrations.py (FINAL VERSION)
import os
from alembic.config import Config
from alembic import command

print("--- Starting database migration script ---")

database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise ValueError("FATAL: DATABASE_URL environment variable is not set.")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

project_dir = os.path.dirname(os.path.abspath(__file__))
alembic_ini_path = os.path.join(project_dir, 'alembic.ini')
alembic_cfg = Config(alembic_ini_path)
alembic_cfg.set_main_option('sqlalchemy.url', database_url)

print(f"--- Running migrations for database: {alembic_cfg.get_main_option('sqlalchemy.url')} ---")
command.upgrade(alembic_cfg, "head")
print("--- Database migrations complete ---")