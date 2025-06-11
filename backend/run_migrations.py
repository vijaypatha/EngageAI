# backend/run_migrations.py (TEMPORARY ROLLBACK SCRIPT)
import os
from alembic.config import Config
from alembic import command

print("--- Starting database migration script ---")

# --- Configuration Setup ---
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise ValueError("FATAL: DATABASE_URL environment variable is not set.")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

project_dir = os.path.dirname(os.path.abspath(__file__))
alembic_ini_path = os.path.join(project_dir, 'alembic.ini')
alembic_cfg = Config(alembic_ini_path)
alembic_cfg.set_main_option('sqlalchemy.url', database_url)
print(f"--- Connection configured for: {alembic_cfg.get_main_option('sqlalchemy.url')} ---")


# --- THIS IS THE CRUCIAL STEP ---
# We are telling alembic to downgrade to the version right BEFORE the broken files.
print("\n--- [ACTION] Downgrading database to revision '0f37aa60ba2b' ---")
command.downgrade(alembic_cfg, "0f37aa60ba2b")
print("\n--- Downgrade complete. The next deployment will upgrade from this point. ---")