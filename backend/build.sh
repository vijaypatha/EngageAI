#!/usr/bin/env bash
# This script is for debugging the Render build environment.
# It will print extra information to the logs.
set -ex

echo "--- Starting build script ---"

# Find the directory where pip installs command-line tools
PYTHON_EXEC=$(which python)
VENV_BIN_DIR=$(dirname "$PYTHON_EXEC")

echo "--- Python's executable directory is: ${VENV_BIN_DIR} ---"

# Explicitly add this directory to the PATH
export PATH="$VENV_BIN_DIR:$PATH"
echo "--- PATH has been set to: ${PATH} ---"

echo "--- Installing dependencies ---"
pip install -r requirements.txt

echo "--- Finished installing dependencies ---"

# CRUCIAL DEBUGGING STEP: List all files in the bin directory
echo "--- Listing all files in ${VENV_BIN_DIR} to find alembic ---"
ls -la "$VENV_BIN_DIR"
echo "--- Finished listing files ---"

echo "--- Now attempting to run alembic ---"
alembic upgrade head

echo "--- Build script finished successfully ---"