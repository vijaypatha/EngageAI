#!/usr/bin/env bash
set -e

echo "--- Installing dependencies ---"
pip install -r requirements.txt

echo "--- Running database migrations via Python script ---"
python run_migrations.py