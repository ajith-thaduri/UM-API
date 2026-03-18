#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting Backend Deployment Process..."

# 1. Run database healing to fix any inconsistent data
echo "🏥 Healing database (cleaning orphaned records)..."
python scripts/db_heal.py

# 2. Run database migrations
echo "🔄 Running database migrations..."
if alembic upgrade head; then
    echo "✅ Migrations completed successfully."
else
    echo "❌ Migrations failed! Attempting to continue anyway, but some features might be broken."
fi

# 3. Start the application
echo "📡 Starting application with Uvicorn..."
# Use the PORT environment variable provided by Render
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
