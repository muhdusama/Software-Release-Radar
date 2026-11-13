"""Published GitHub repository security advisories, matched to the installed version.

Advisories are read from ``/repos/{owner}/{repo}/security-advisories`` at most once
a day per tracker, after a successful release check. Matching is deterministic:

* A repository can publish advisories for other components (Gitea, for example,
  publishes advisories for its runner). An advisory only counts against the
  tracked software when one of its patched versions or range bounds is a known
  release of this tracker. Otherwise it is shown as applying to its component.
* The installed version is compared with each vulnerable range, such as
  ``>= 1.19.0, <= 28.2.0``. When either side cannot be parsed the status is
  ``unknown``, never ``not affected``.

Advisory text is untrusted and is rendered escaped.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from .db import connect, transaction, utcnow
from .github import _github_get, forge_for, normalise_repository
from .tracker_utils import parse_utc
from .versioning import _pad_core, _structured_version, versions_match

LOGGER = logging.getLogger(__name__)
REFRESH_HOURS = 24
MAX_ADVISORIES = 100
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_CONSTRAINT_RE = re.compile(r"^\s*(<=|>=|<|>|=)?\s*(\S+)\s*$")


def _version_key(value: str | None):
    parsed = _structured_version(value) if value else None
    return _pad_core(parsed["core"]) if parsed else None


def _compare(left: str | None, right: str | None) -> int | None:
    a, b = _version_key(left), _version_key(right)
    if a is None or b is None:
        return None
    return (a > b) - (a < b)


def in_range(version: str | None, vulnerable_range: str | None) -> bool | None:
    """True, False or None (cannot tell) for a GitHub range like '>= 1.0, < 1.5'."""
    if not version or not vulnerable_range:
        return None
    for part in str(vulnerable_range).split(","):
        match = _CONSTRAINT_RE.match(part)
        if not match:
            return None
        operator, bound = match.group(1) or "=", match.group(2)
        result = _compare(version, bound)
        if result is None:
            return None
        if not {"<": result < 0, "<=": result <= 0, ">": result > 0, ">=": result >= 0, "=": result == 0}[operator]:
            return False
    return True


def _range_versions(vulnerability: dict) -> list[str]:
    values = [item.strip() for item in str(vulnerability.get("patched_versions") or "").split(",") if item.strip()]
    for part in str(vulnerability.get("vulnerable_version_range") or "").split(","):
        match = _CONSTRAINT_RE.match(part)
        if match:
            values.append(match.group(2))
    return values


def _project(payload: dict) -> dict | None:
    ghsa = str(payload.get("ghsa_id") or "").strip()
    if not re.fullmatch(r"GHSA(?:-[23456789cfghjmpqrvwx]{4}){3}", ghsa):
        return None
    severity = str(payload.get("severity") or "").lower()
    vulnerabilities = []
    for item in (payload.get("vulnerabilities") or [])[:20]:
        if not isinstance(item, dict):
            continue
        package = item.get("package") if isinstance(item.get("package"), dict) else {}
        vulnerabilities.append({
            "package": str(package.get("name") or "")[:200],
            "vulnerable_version_range": str(item.get("vulnerable_version_range") or "")[:200],
            "patched_versions": str(item.get("patched_versions") or "")[:200],
        })
    url = str(payload.get("html_url") or "")
    return {
        "ghsa_id": ghsa,
        "cve_id": (str(payload.get("cve_id") or "")[:40] or None),
        "severity": severity if severity in SEVERITY_ORDER else "unknown",
        "summary": str(payload.get("summary") or "")[:300],
        "url": url if url.startswith("https://github.com/") else f"https://github.com/advisories/{ghsa}",
        "published_at": str(payload.get("published_at") or "")[:40] or None,
        "vulnerabilities": vulnerabilities,
    }


def fetch_advisories(repository: str) -> list[dict]:
    owner, repo = normalise_repository(repository).split("/", 1)
    payload = _github_get(f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"
                          f"/security-advisories?state=published&per_page={MAX_ADVISORIES}")
    if not isinstance(payload, list):
        raise ValueError("GitHub returned an unexpected advisory response.")
    return [item for item in (_project(entry) for entry in payload if isinstance(entry, dict)) if item]


def refresh_due(tracker) -> bool:
    if forge_for(tracker["repository"]) is not None:
        return False
    checked = parse_utc(tracker["advisories_checked_at"])
    return checked is None or checked <= datetime.now(timezone.utc) - timedelta(hours=REFRESH_HOURS)


def refresh_tracker_advisories(tracker) -> int:
    """Replace the stored advisories for one GitHub tracker. Raises on fetch errors."""
    advisories = fetch_advisories(tracker["repository"])
    now = utcnow()
    with transaction() as conn:
        conn.execute("DELETE FROM security_advisories WHERE tracker_id = ?", (tracker["id"],))
        conn.executemany(
            "INSERT OR REPLACE INTO security_advisories(tracker_id, ghsa_id, cve_id, severity, summary, url, published_at,"
            " vulnerabilities_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(tracker["id"], item["ghsa_id"], item["cve_id"], item["severity"], item["summary"], item["url"],
              item["published_at"], json.dumps(item["vulnerabilities"], separators=(",", ":")), now) for item in advisories],
        )
        conn.execute("UPDATE trackers SET advisories_checked_at = ? WHERE id = ?", (now, tracker["id"]))
    return len(advisories)


def refresh_due_advisories(limit: int = 5) -> dict[str, int]:
    """Refresh a few trackers whose advisories are over a day old. Called by the scheduler."""
    from .github import shared_rate_limit_until

    cooldown = shared_rate_limit_until()
    if cooldown and cooldown > datetime.now(timezone.utc):
        return {"refreshed": 0, "failed": 0}
    with connect() as conn:
        rows = conn.execute("SELECT * FROM trackers WHERE enabled = 1 AND last_status = 'ok' "
                            "ORDER BY COALESCE(advisories_checked_at, '') , id").fetchall()
    refreshed = failed = 0
    for tracker in rows:
        if refreshed + failed >= limit:
            break
        if not refresh_due(tracker):
            continue
        try:
            refresh_tracker_advisories(tracker)
            refreshed += 1
        except Exception as exc:  # advisories are supplementary; the next cycle retries
            failed += 1
            LOGGER.warning("Could not refresh security advisories for %s: %s", tracker["repository"], exc)
            with transaction() as conn:  # back off for a day rather than retrying every minute
                conn.execute("UPDATE trackers SET advisories_checked_at = ? WHERE id = ?", (utcnow(), tracker["id"]))
    return {"refreshed": refreshed, "failed": failed}


def evaluate(advisory: dict, installed: str | None, target: str | None, known_versions: list[str]) -> dict:
    """Return the advisory with status: affected, fixed, not_affected, unknown or other_component."""
    def known(version: str) -> bool:
        return any(versions_match(version, None, release) for release in known_versions)

    own = [v for v in advisory["vulnerabilities"] if any(known(value) for value in _range_versions(v))]
    if not own:
        packages = sorted({v["package"] for v in advisory["vulnerabilities"] if v["package"]})
        return {**advisory, "status": "other_component", "packages": packages, "fixed_in": None, "target_fixes": None}
    fixed_in = next((p.strip() for v in own for p in v["patched_versions"].split(",") if p.strip()), None)
    target_fixes = None
    if target and own:
        target_results = [in_range(target, v["vulnerable_version_range"]) for v in own]
        target_fixes = None if None in target_results else not any(target_results)
    if not installed:
        status = "unknown"
    else:
        results = [in_range(installed, v["vulnerable_version_range"]) for v in own]
        status = "affected" if any(results) else "unknown" if None in results else "not_affected"
    return {**advisory, "status": status, "packages": sorted({v["package"] for v in own if v["package"]}),
            "fixed_in": fixed_in, "target_fixes": target_fixes}


def _known_versions(conn, tracker_ids: list[int]) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {tracker_id: [] for tracker_id in tracker_ids}
    if not tracker_ids:
        return result
    marks = ",".join("?" for _ in tracker_ids)
    for row in conn.execute(f"SELECT tracker_id, version FROM events WHERE tracker_id IN ({marks})", tracker_ids):
        result[int(row["tracker_id"])].append(str(row["version"]))
    for row in conn.execute(f"SELECT id, current_version FROM trackers WHERE id IN ({marks})", tracker_ids):
        if row["current_version"]:
            result[int(row["id"])].append(str(row["current_version"]))
    return result


def advisories_for(trackers: list[dict]) -> dict[int, list[dict]]:
    """Evaluated advisories per tracker id, most severe and affected first."""
    ids = [int(t["id"]) for t in trackers]
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM security_advisories WHERE tracker_id IN ({marks})", ids).fetchall()
        known = _known_versions(conn, ids)
    by_id = {int(t["id"]): t for t in trackers}
    result: dict[int, list[dict]] = {tracker_id: [] for tracker_id in ids}
    for row in rows:
        tracker = by_id[int(row["tracker_id"])]
        try:
            vulnerabilities = json.loads(row["vulnerabilities_json"])
        except ValueError:
            vulnerabilities = []
        advisory = {key: row[key] for key in ("ghsa_id", "cve_id", "severity", "summary", "url", "published_at")}
        advisory["vulnerabilities"] = vulnerabilities if isinstance(vulnerabilities, list) else []
        installed = tracker.get("detected_installed_version") or tracker.get("installed_version")
        target = tracker.get("current_version") or tracker.get("current_release_name")
        result[int(row["tracker_id"])].append(evaluate(advisory, installed, target, known[int(row["tracker_id"])]))
    status_rank = {"affected": 0, "unknown": 1, "not_affected": 2, "other_component": 3}
    for items in result.values():
        items.sort(key=lambda a: a["published_at"] or "", reverse=True)  # newest first within a group
        items.sort(key=lambda a: (status_rank.get(a["status"], 9), SEVERITY_ORDER.get(a["severity"], 9)))
    return result


def affected_summary(advisories: list[dict]) -> dict[str, object]:
    affected = [a for a in advisories if a["status"] == "affected"]
    worst = min((SEVERITY_ORDER.get(a["severity"], 9) for a in affected), default=None)
    return {"affected": len(affected),
            "worst": next((name for name, rank in SEVERITY_ORDER.items() if rank == worst), None)}
