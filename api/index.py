"""Vercel serverless entry point. Vercel's Python runtime detects the exported
ASGI `app` and serves it; vercel.json rewrites every path to this function."""

from app.main import app  # noqa: F401
