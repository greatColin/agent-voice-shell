#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "Starting Agent Voice Shell..."

if ! command -v pi &> /dev/null; then
    echo "Error: pi command not found. Please install Pi first:"
    echo "  npm i -g @earendil-works/pi-coding-agent"
    exit 1
fi

echo "Starting server on http://localhost:8000"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
