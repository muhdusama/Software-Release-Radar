from __future__ import annotations

from flask import Flask

from .web import create_app as create_web_app


def create_app() -> Flask:
    """Create the public application. Kept as the Gunicorn entry point."""
    return create_web_app()
