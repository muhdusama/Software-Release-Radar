from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlparse

DECISION_CHOICES = (
    ("review", "Review"),
    ("update", "Update"),
    ("wait", "Wait"),
    ("ignore", "Ignore"),
    ("deployed", "Deployed"),
)
PRIORITY_CHOICES = (
    ("low", "Low"),
    ("normal", "Normal"),
    ("high", "High"),
    ("urgent", "Urgent"),
)
RISK_CHOICES = (
    ("unknown", "Not assessed"),
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("critical", "Critical"),
)

DECISION_VALUES = {value for value, _ in DECISION_CHOICES}
PRIORITY_VALUES = {value for value, _ in PRIORITY_CHOICES}
RISK_VALUES = {value for value, _ in RISK_CHOICES}


def release_key(tracker) -> str:
    return str(tracker.get("current_version") or tracker.get("current_release_name") or "").strip()


def validate_choice(value: str | None, allowed: set[str], label: str) -> str:
    normalised = str(value or "").strip().lower()
    if normalised not in allowed:
        raise ValueError(f"Invalid {label.lower()}.")
    return normalised


def validate_maintenance_date(value: str | None) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Maintenance date must use YYYY-MM-DD.") from exc
    return value


def validate_change_record_url(value: str | None) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https", "obsidian"}:
        raise ValueError("Change record link must use http://, https:// or obsidian://.")
    if parsed.scheme in {"http", "https"} and not parsed.netloc:
        raise ValueError("Change record link must be a complete URL.")
    return value


def checklist_from_form(lines_value: str | None, completed_values: list[str]) -> list[dict[str, object]]:
    completed = {int(item) for item in completed_values if str(item).isdigit()}
    items: list[dict[str, object]] = []
    for raw in str(lines_value or "").splitlines():
        text = raw.strip()
        if not text:
            continue
        if len(text) > 240:
            raise ValueError("Checklist items must be 240 characters or fewer.")
        if len(items) >= 30:
            raise ValueError("A checklist can contain at most 30 items.")
        items.append({"text": text, "done": len(items) in completed})
    return items


def checklist_json(items: list[dict[str, object]]) -> str:
    return json.dumps(items, ensure_ascii=False, separators=(",", ":"))


def load_checklist(value: str | None) -> list[dict[str, object]]:
    try:
        raw = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    result: list[dict[str, object]] = []
    if not isinstance(raw, list):
        return result
    for item in raw[:30]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if text:
            result.append({"text": text[:240], "done": bool(item.get("done"))})
    return result


def checklist_summary(items: list[dict[str, object]]) -> dict[str, int]:
    total = len(items)
    complete = sum(1 for item in items if item.get("done"))
    return {"total": total, "complete": complete, "percent": round((complete / total) * 100) if total else 0}
