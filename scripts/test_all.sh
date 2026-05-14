#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
.venv/bin/python -m compileall backend/app livekit_worker
cd backend
DATABASE_URL= SARVAM_API_KEY= LIVEKIT_URL= LIVEKIT_API_KEY= LIVEKIT_API_SECRET= \
    ../.venv/bin/python -m unittest discover tests
cd ../frontend
npm run build
npm audit --audit-level=moderate
