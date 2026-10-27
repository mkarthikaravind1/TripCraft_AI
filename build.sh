#!/usr/bin/env bash
# Render build script: install, collect static files, apply migrations (which also seed the FAQs).
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py seed_faqs
