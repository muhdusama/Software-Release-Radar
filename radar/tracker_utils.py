from __future__ import annotations

import re
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone

from .db import ALLOWED_REFRESH_HOURS, DEFAULT_REFRESH_HOURS
from .github import normalise_repository

TAG_RE = re.compile(r"[^a-z0-9._-]+")


def safe_optional_url(value: str | None, label: str = 'URL') -> str | None:
    value = (value or '').strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError(f'{label} must be a complete http:// or https:// URL.')
    return value


def validate_tracker_core(values: dict[str, object], *, existing=None) -> dict[str, object]:
    result = dict(values)
    if 'repository' in result:
        result['repository'] = normalise_repository(result['repository'])
    if 'homepage_url' in result:
        result['homepage_url'] = safe_optional_url(result['homepage_url'], 'Homepage')
    if 'refresh_hours' in result:
        result['refresh_hours'] = validate_refresh_hours(result['refresh_hours'])
    if 'name' in result:
        result['name'] = str(result['name'] or '').strip()
        if not result['name']:
            raise ValueError('Software name is required.')
        if len(result['name']) > 120:
            raise ValueError('Software name must be 120 characters or fewer.')
    if 'strategy' in result and result['strategy'] not in {'release', 'tag'}:
        raise ValueError('Invalid tracking strategy.')
    if 'tags' in result:
        result['tags'] = normalise_tags(result['tags'])
    for key in ('notes', 'installed_version'):
        if key in result:
            result[key] = (result[key] or '').strip() or None
    return result


def reset_release_state(conn, tracker_id: int, *, clear_last_checked: bool) -> None:
    conn.execute('''UPDATE trackers SET current_version=NULL,current_release_name=NULL,
        current_release_url=NULL,current_release_body=NULL,current_published_at=NULL,
        last_status=NULL,last_error=NULL,github_retry_at=NULL,
        last_checked_at=CASE WHEN ? THEN NULL ELSE last_checked_at END WHERE id=?''',
        (clear_last_checked, tracker_id))


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


def next_due_at(last_checked_at: str | None, refresh_hours: int,
                now: datetime | None = None, *, retry_at: str | None = None) -> datetime:
    retry = parse_utc(retry_at)
    if retry is not None:
        return retry
    last = parse_utc(last_checked_at)
    if last is None:
        return now or datetime.now(timezone.utc)
    return last + timedelta(hours=refresh_hours)


def is_due(last_checked_at: str | None, refresh_hours: int,
           now: datetime | None = None, *, retry_at: str | None = None) -> bool:
    if parse_utc(retry_at) is None and parse_utc(last_checked_at) is None:
        return True
    now = now or datetime.now(timezone.utc)
    return next_due_at(last_checked_at, refresh_hours, now, retry_at=retry_at) <= now
