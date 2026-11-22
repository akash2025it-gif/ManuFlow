#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

# Install production dependencies
pip install -r requirements.txt

# Apply database migrations
python manage.py migrate --no-input

# Seed or verify the official ManuFlow demonstration account and enterprise data
python manage.py seed_demo_account
python manage.py seed_enterprise_demo_data

# Collect static files for WhiteNoise
python manage.py collectstatic --no-input
