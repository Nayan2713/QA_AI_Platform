#!/bin/bash
set -e

# Function to wait for Postgres
wait_for_postgres() {
  if [ -n "$DB_HOST" ]; then
    echo "Waiting for PostgreSQL at $DB_HOST:$DB_PORT..."
    # pg_isready returns 0 if PostgreSQL is accepting connections, 1 or 2 otherwise
    until pg_isready -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "${DB_USER:-postgres}" >/dev/null 2>&1; do
      echo "PostgreSQL is unavailable - sleeping"
      sleep 1
    done
    echo "PostgreSQL is up and running!"
  fi
}

# Function to wait for Redis
wait_for_redis() {
  if [ -n "$CELERY_BROKER_URL" ]; then
    echo "Waiting for Redis to be reachable..."
    python -c "
import socket
import time
import os
from urllib.parse import urlparse

broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
parsed = urlparse(broker_url)
host = parsed.hostname or 'redis'
port = parsed.port or 6379

print(f'Checking Redis at {host}:{port}...')
while True:
    try:
        s = socket.create_connection((host, port), timeout=1)
        s.close()
        print('Redis is up and running!')
        break
    except (socket.error, socket.timeout):
        print('Redis is unavailable - sleeping')
        time.sleep(1)
"
  fi
}

wait_for_postgres
wait_for_redis

# Run database migrations and collectstatic for Django web/Gunicorn processes
if [[ "$*" == *"manage.py runserver"* ]] || [[ "$*" == *"gunicorn"* ]]; then
  echo "Running database migrations..."
  python manage.py migrate --noinput

  echo "Collecting static files..."
  python manage.py collectstatic --noinput

  echo "Creating cache tables if needed..."
  python manage.py createcachetable || echo "Skipping createcachetable (no database cache configured)"
fi

# Execute the main container command
exec "$@"
