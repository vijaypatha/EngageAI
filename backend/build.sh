#!/usr/bin/env bash
# exit on error
set -e

# Install Python dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head