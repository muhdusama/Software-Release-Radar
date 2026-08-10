from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .db import ALLOWED_REFRESH_HOURS, DEFAULT_REFRESH_HOURS

TAG_RE = re.compile(r"[^a-z0-9._-]+")


def normalise_tags(value: str | list[str] | tuple[str, ...] | None) -> str:
    if value is None:
        return ""
    raw_items = value if isinstance(value, (list, tuple)) else str(value).split(",")
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        tag = TAG_RE.sub("-", str(item).strip().lower()).strip("-._")
        if not tag or tag in seen:
            continue
        if len(tag) > 32:
            tag = tag[:32].rstrip("-._")
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
        if len(tags) >= 12:
            break
    return ",".join(tags)


def split_tags(value: str | None) -> list[str]:
    return [item for item in str(value or "").split(",") if item]


def validate_refresh_hours(value: int | str | None) -> int:
    if value in (None, ""):
        return DEFAULT_REFRESH_HOURS
    try:
        hours = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Refresh interval must be a whole number of hours.") from exc
    if hours not in ALLOWED_REFRESH_HOURS:
        allowed = ", ".join(str(item) for item in ALLOWED_REFRESH_HOURS)
        raise ValueError(f"Refresh interval must be one of: {allowed} hours.")
    return hours


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def next_due_at(last_checked_at: str | None, refresh_hours: int) -> datetime:
    last = parse_utc(last_checked_at)
    if last is None:
        return datetime.now(timezone.utc)
    return last + timedelta(hours=refresh_hours)


def is_due(last_checked_at: str | None, refresh_hours: int, now: datetime | None = None) -> bool:
    if parse_utc(last_checked_at) is None:
        return True
    now = now or datetime.now(timezone.utc)
    return next_due_at(last_checked_at, refresh_hours) <= now
