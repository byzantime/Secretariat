#!/bin/sh
set -e

# Create data directory if it doesn't exist
mkdir -p "${DATA_DIR:-/app/data}"

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

# Start app
echo "Starting application..."
exec hypercorn main:app --bind 0.0.0.0:8080
