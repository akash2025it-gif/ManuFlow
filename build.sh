#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

# Install production dependencies
pip install -r requirements.txt

# Apply database migrations
python manage.py migrate --no-input

# Seed or verify the official ManuFlow demonstration account
python manage.py seed_demo_account

# Collect static files for WhiteNoise
python manage.py collectstatic --no-input
