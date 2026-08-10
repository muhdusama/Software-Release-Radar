from __future__ import annotations

from flask import Flask

from .auth_rate_limit import install_auth_rate_limits
from .web import create_app as create_web_app


def create_app() -> Flask:
    """Create the public application with production security extensions."""
    app = create_web_app()
    install_auth_rate_limits(app)
    return app
