from __future__ import annotations

import os
import re
from functools import wraps
from typing import Any

from flask import Flask

_GIT_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")


def build_commit() -> str | None:
    """Return the validated source revision embedded in this build, when available."""
    value = os.environ.get("RADAR_BUILD_COMMIT", "").strip()
    if not _GIT_COMMIT_RE.fullmatch(value):
        return None
    return value.lower()


def install_build_metadata(app: Flask) -> None:
    """Add the validated source revision to the existing health response."""
    health_view = app.view_functions.get("healthz")
    if health_view is None:
        raise RuntimeError(
            "The healthz endpoint must be registered before build metadata is installed."
        )

    @wraps(health_view)
    def healthz_with_build_metadata(*args: Any, **kwargs: Any):
        result = health_view(*args, **kwargs)
        commit = build_commit()
        if commit and isinstance(result, dict):
            payload = dict(result)
            payload["commit"] = commit
            return payload
        return result

    app.view_functions["healthz"] = healthz_with_build_metadata
