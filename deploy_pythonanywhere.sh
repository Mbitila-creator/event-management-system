#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/Mbitila/registration"

cd "$PROJECT_DIR"
source "$PROJECT_DIR/venv/bin/activate"

echo "Creating a database backup..."
python manage.py backup_database

echo "Downloading the latest approved code..."
git pull --ff-only

echo "Updating Python packages..."
python -m pip install -r requirements.txt

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Compiling Kiswahili translations..."
python manage.py compilemessages -l sw --ignore='venv/*'

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Running the Django system check..."
python manage.py check

echo "Update complete. Reload the web app from the PythonAnywhere Web tab."
