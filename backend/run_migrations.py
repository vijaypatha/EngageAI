# backend/run_migrations.py

import os
from alembic.config import Config
from alembic import command

print("--- Starting database migration script ---")

# Get the directory of the current script
# This makes the path to alembic.ini relative and robust
project_dir = os.path.dirname(os.path.abspath(__file__))
alembic_ini_path = os.path.join(project_dir, 'alembic.ini')

# Create an Alembic configuration object
alembic_cfg = Config(alembic_ini_path)

# Programmatically run the 'upgrade' command
command.upgrade(alembic_cfg, "head")

print("--- Database migrations complete ---")