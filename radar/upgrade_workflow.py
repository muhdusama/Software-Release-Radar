from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlparse
from .db import audit, transaction, utcnow

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


def save_upgrade_review(tracker_id: int, submitted_release_key: str, expected_revision: int,
                        review: dict[str, object], *, user_id: int, mark_deployed: bool = False,
                        conn=None) -> dict[str, object]:
    if (type(expected_revision) is not int or expected_revision < 0 or not isinstance(submitted_release_key, str)
            or not 1 <= len(submitted_release_key.strip()) <= 240):
        raise ValueError('Release and revision are required; reload the decision.')
    if conn is None:
        with transaction(immediate=True) as own:
            return save_upgrade_review(tracker_id, submitted_release_key, expected_revision, review,
                                       user_id=user_id, mark_deployed=mark_deployed, conn=own)
    if not conn.in_transaction:
        raise ValueError('An active transaction is required.')
    allowed = {'decision_status', 'priority', 'risk', 'maintenance_date', 'checklist', 'rollback_notes', 'change_record_url', 'decision_notes'}
    if not isinstance(review, dict) or set(review) - allowed:
        raise ValueError('Invalid review fields.')
    status = validate_choice(review.get('decision_status', 'review'), DECISION_VALUES - {'deployed'}, 'Decision')
    priority = validate_choice(review.get('priority', 'normal'), PRIORITY_VALUES, 'Priority')
    risk = validate_choice(review.get('risk', 'unknown'), RISK_VALUES, 'Risk')
    maintenance = validate_maintenance_date(review.get('maintenance_date'))
    url = validate_change_record_url(review.get('change_record_url'))
    if url and len(url) > 2048:
        raise ValueError('Change record link must be 2048 characters or fewer.')
    notes = {}
    for key in ('rollback_notes', 'decision_notes'):
        value = review.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 10000):
            raise ValueError('Notes must be 10000 characters or fewer.')
        notes[key] = (value or '').strip() or None
    checklist = review.get('checklist', [])
    if not isinstance(checklist, list) or len(checklist) > 30:
        raise ValueError('Invalid checklist.')
    for item in checklist:
        if (not isinstance(item, dict) or set(item) != {'text', 'done'} or not isinstance(item['text'], str)
                or not 1 <= len(item['text'].strip()) <= 240 or type(item['done']) is not bool):
            raise ValueError('Invalid checklist item.')
    owner = conn.execute('SELECT role,active FROM users WHERE id=?', (user_id,)).fetchone()
    if not owner or not owner['active'] or owner['role'] != 'admin':
        raise ValueError('Administrator access is required.')
    row = conn.execute('SELECT * FROM trackers WHERE id=?', (tracker_id,)).fetchone()
    if row is None:
        raise ValueError('Tracker is unavailable.')
    tracker = dict(row)
    key = submitted_release_key.strip()
    existing = conn.execute('SELECT * FROM upgrade_decisions WHERE tracker_id=? AND release_version=?', (tracker_id, key)).fetchone()
    historical = key != release_key(tracker)
    if (historical and not existing) or (historical and mark_deployed):
        raise ValueError('Release changed; reload the decision. Historical decisions cannot be marked deployed.')
    if (existing and (existing['revision'] != expected_revision or existing['decision_status'] == 'deployed')) or (not existing and expected_revision != 0):
        raise ValueError('Decision changed or is deployed; reload the decision.')
    installed = (existing['installed_version_at_decision'] if existing else None) or tracker.get('detected_installed_version') or tracker.get('installed_version')
    name = (existing['release_name'] if existing else None) or tracker.get('current_release_name') or key
    now = utcnow()
    values = {'release_name': name, 'installed_version_at_decision': installed,
        'decision_status': 'deployed' if mark_deployed else status, 'priority': priority, 'risk': risk,
        'maintenance_date': maintenance, 'checklist_json': checklist_json(checklist), **notes,
        'change_record_url': url, 'updated_at': now, 'updated_by': user_id}
    if mark_deployed:
        values.update(previous_version=installed, deployed_version=key, deployed_at=now)
    if existing:
        assignments = ','.join(f'{field}=?' for field in values)
        cursor = conn.execute(f"UPDATE upgrade_decisions SET {assignments},revision=revision+1 WHERE id=? AND revision=? AND decision_status<>'deployed'",
                              [*values.values(), existing['id'], expected_revision])
        if cursor.rowcount != 1:
            raise ValueError('Decision changed; reload the decision.')
        decision_id = existing['id']
    else:
        columns = ','.join(values)
        placeholders = ','.join('?' for _ in values)
        cursor = conn.execute(f'INSERT INTO upgrade_decisions({columns},tracker_id,release_version,created_at,revision) VALUES({placeholders},?,?,?,1)',
                              [*values.values(), tracker_id, key, now])
        decision_id = int(cursor.lastrowid)
    audit(user_id, 'upgrade_deployed' if mark_deployed else 'upgrade_decision_saved', 'upgrade_decision',
          decision_id, f"{tracker['name']} {key}: {values['decision_status']}", conn=conn)
    return dict(conn.execute('SELECT * FROM upgrade_decisions WHERE id=?', (decision_id,)).fetchone())
