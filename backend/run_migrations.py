# backend/run_migrations.py

import os
from alembic.config import Config
from alembic import command

print("--- Starting database migration script ---")

# 1. Directly get the database URL from the environment variables
database_url = os.getenv("DATABASE_URL")

# Raise an error if the environment variable isn't set
if not database_url:
    raise ValueError("FATAL: DATABASE_URL environment variable is not set.")

# Render uses "postgres://", but SQLAlchemy needs "postgresql://"
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# Set the path to the alembic.ini file
project_dir = os.path.dirname(os.path.abspath(__file__))
alembic_ini_path = os.path.join(project_dir, 'alembic.ini')
alembic_cfg = Config(alembic_ini_path)

# 2. Forcefully set the database URL in Alembic's configuration.
#    This overrides any value in the alembic.ini file itself.
alembic_cfg.set_main_option('sqlalchemy.url', database_url)

print(f"--- Migrating database connection configured for: {alembic_cfg.get_main_option('sqlalchemy.url')} ---")
command.upgrade(alembic_cfg, "head")
print("--- Database migrations complete ---")