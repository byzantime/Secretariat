#!/bin/bash
set -e

# Start app
echo "Starting application..."
exec hypercorn main:app --bind 0.0.0.0:8080
