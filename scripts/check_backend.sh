#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../backend"
../.venv/bin/python -m compileall app tests
DATABASE_URL= SARVAM_API_KEY= LIVEKIT_URL= LIVEKIT_API_KEY= LIVEKIT_API_SECRET= \
    ../.venv/bin/python -m unittest discover tests
