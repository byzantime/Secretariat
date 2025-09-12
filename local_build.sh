#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Ensure we're in the project root directory
cd "$(dirname "$0")"

# Activate virtual environment (assuming it's in the current directory)
source .venv/bin/activate

# Install npm packages
npm install

# Build and minify Tailwind CSS
npx tailwindcss -i ./src/static/css/input.css -o ./src/static/css/styles.css --minify

# Start the Quart (local development only) server
python main.py
