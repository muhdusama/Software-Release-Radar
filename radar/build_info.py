from __future__ import annotations

import os
import re

_GIT_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")


def build_commit() -> str | None:
    """Return the validated source revision embedded in this build, when available."""
    value = os.environ.get("RADAR_BUILD_COMMIT", "").strip()
    if not _GIT_COMMIT_RE.fullmatch(value):
        return None
    return value.lower()
