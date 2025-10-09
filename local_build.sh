#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Ensure we're in the project root directory
cd "$(dirname "$0")"

# Activate virtual environment (assuming it's in the current directory)
source .venv/bin/activate

# Install npm packages (offline mode)
npm ci --offline

# Build and minify Tailwind CSS
npm run build

# Run database migrations
alembic upgrade head

# Start the Quart server with auto-restart on clean exit
# Ctrl+C (SIGINT) will break out of the loop and exit completely
echo "Starting application with auto-restart on settings changes..."
echo "Press Ctrl+C to stop the application completely."
echo ""

# Trap SIGINT (Ctrl+C) to exit cleanly
trap 'echo ""; echo "Received Ctrl+C, shutting down..."; exit 0' SIGINT

while true; do
    echo "$(date '+%Y-%m-%d %H:%M:%S'): Starting Secretariat..."

    # Run the app and capture exit code
    # Don't use 'set -e' here so we can handle the exit code
    set +e
    python main.py
    EXIT_CODE=$?
    set -e

    echo "$(date '+%Y-%m-%d %H:%M:%S'): Application exited with code $EXIT_CODE"

    # If exit code is 0 (clean shutdown for restart), restart immediately
    if [ $EXIT_CODE -eq 0 ]; then
        echo "Clean shutdown detected (settings update). Restarting immediately..."
        sleep 1
    else
        # For other exit codes, don't auto-restart in local dev
        # (likely a crash or intentional shutdown)
        echo "Application exited unexpectedly. Stopping."
        exit $EXIT_CODE
    fi
done
