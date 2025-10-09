#!/bin/sh
set -e

# Create data directory if it doesn't exist
mkdir -p "${DATA_DIR:-/app/data}"

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

# Start app with auto-restart loop
# When the app exits (e.g., after settings change), it will automatically restart
echo "Starting application with auto-restart..."
while true; do
    echo "$(date): Starting Secretariat..."
    hypercorn main:app --bind 0.0.0.0:8080

    # Capture exit code
    EXIT_CODE=$?

    echo "$(date): Application exited with code $EXIT_CODE"

    # If exit code is 0 (clean shutdown for restart), restart immediately
    # For other exit codes, wait a bit before restarting to avoid crash loops
    if [ $EXIT_CODE -eq 0 ]; then
        echo "Clean shutdown detected (settings update). Restarting immediately..."
        sleep 1
    else
        echo "Unexpected exit. Waiting 5 seconds before restart..."
        sleep 5
    fi
done
