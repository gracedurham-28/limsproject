#!/usr/bin/env bash
set -e
cd /app
# Ensure .env values are available to manage.py
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi
python manage.py migrate
python manage.py collectstatic --noinput
exec "$@"
