"""
Vercel serverless entry point for FastAPI.

Vercel's Python runtime expects a module-level `app` ASGI instance.
We import the existing FastAPI app and export it here so `vercel.json`
can point `builds[].src` at this file.
"""
import sys
import os

# Backend package lives one level up from this file (backend/app/)
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.main import app  # noqa: F401 — Vercel picks up the `app` name

__all__ = ["app"]
