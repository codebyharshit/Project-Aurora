#!/bin/sh
# Seed the persistent volume (case database, extraction cache) on first start.
mkdir -p /app/data/state
if [ ! -f /app/data/state/soony/aurora.sqlite ]; then
  cp -r /app/seed/state/. /app/data/state/
fi
cd /app/backend && exec uvicorn aurora.api:app --host 0.0.0.0 --port "${PORT:-8000}"
