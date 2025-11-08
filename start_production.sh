#!/bin/bash
set -e

echo "🚀 Starting Audiobook Manager in Production Mode"

cd /opt/audiobook-manager

# Activate virtual environment
source venv/bin/activate

# Validate configuration
echo "🔧 Validating configuration..."
if ! python -c "from app.config_validator import ConfigValidator; exit(0 if ConfigValidator.validate() else 1)"; then
    echo "❌ Configuration validation failed!"
    exit 1
fi

# Check disk space
echo "💾 Checking disk space..."
if ! python -c "import asyncio; from app.system_monitor import SystemMonitor; exit(0 if asyncio.run(SystemMonitor.check_disk_space()) else 1)"; then
    echo "⚠️  Low disk space warning!"
fi

# Start the application
echo "🎧 Starting Audiobook Manager..."
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 2 \
    --access-log \
    --no-server-header