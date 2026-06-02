#!/bin/bash
set -e

# Kill background processes on exit
trap "kill 0" EXIT

echo "Starting Mycelium Backend (FastAPI)..."
uv run python -m server.main &

echo "Starting Mycelium Frontend (Vite)..."
cd ui && npm run dev -- --host 0.0.0.0 &

# Wait for all processes to finish
wait
