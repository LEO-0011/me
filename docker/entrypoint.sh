#!/bin/bash
set -e

# Create necessary directories
mkdir -p /downloads /app/data

# Set proper permissions
chown -R botuser:botuser /downloads /app/data 2>/dev/null || true

# Clean up any leftover temporary files from previous runs
find /downloads -type f -mmin +60 -delete 2>/dev/null || true

echo "==================================="
echo "  MEGA to Telegram Bot"
echo "==================================="
echo "Storage Path: ${STORAGE_PATH:-/downloads}"
echo "Database Path: ${DB_PATH:-/app/data/bot.db}"
echo "==================================="

# Run the bot
exec python main.py "$@"
