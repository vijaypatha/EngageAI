#!/usr/bin/env bash
# exit on error
set -e

# Manually add the Python virtual environment's bin directory to the PATH.
# This is the crucial step that forces the shell to find the 'alembic' command.
export PATH="/opt/render/project/src/.venv/bin:$PATH"

# Install Python dependencies
pip install -r requirements.txt

# Run database migrations
# Now that the PATH is correctly set, this command will be found.
alembic upgrade head