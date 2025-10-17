#!/bin/bash
# start.sh - Startup script for Render deployment

echo "🚀 Starting LLM Deployment System..."

# Set production environment
export PYTHONUNBUFFERED=1

# Run database migrations if you had any (not needed for this project)
# python migrate.py

# Start uvicorn with Render's PORT environment variable
echo "Starting server on port ${PORT:-8000}..."
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
