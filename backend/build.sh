#!/usr/bin/env bash
# Render build step: install, collect static files, apply migrations, seed demo data once.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  python manage.py seed_demo   # no-op when data already exists
fi
