from __future__ import annotations

import re
from collections.abc import Mapping

_VERSION_RE = re.compile(r"(?<![A-Za-z0-9])v?(\d+(?:\.\d+){1,4}(?:[-+._][A-Za-z0-9.-]+)?)", re.IGNORECASE)
_STRUCTURED_RE = re.compile(r"^v?(?P<core>\d+(?:\.\d+){1,4})(?P<suffix>[-+._][A-Za-z0-9.-]+)?$", re.IGNORECASE)
_LS_RE = re.compile(r"(?:^|[-+._])ls(?P<build>\d+)(?:$|[-+._])", re.IGNORECASE)
_RC_RE = re.compile(r"(?:^|[-+._])rc[.-]?(?P<build>\d+)(?:$|[-+._])", re.IGNORECASE)
_NUMERIC_SUFFIX_RE = re.compile(r"^[-+._](?P<build>\d+)$")

ATTENTION_REASON_LABELS = {
    "checker_error": "Checker error",
    "offline": "Service offline",
    "upstream_unavailable": "Upstream version unavailable",
    "comparison_unavailable": "Version comparison unavailable",
}


def canonical_version(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    value = value.rsplit("/", 1)[-1]
    if "@sha256:" in value:
        return value.lower()
    if ":" in value and not value.startswith("http"):
        value = value.rsplit(":", 1)[-1]
    value = value.strip().lower()
    if value.startswith("v") and len(value) > 1 and value[1].isdigit():
        value = value[1:]
    return value


def version_candidates(*values: str | None) -> set[str]:
    candidates: set[str] = set()
    for value in values:
        raw = (value or "").strip()
        if not raw:
            continue
        canonical = canonical_version(raw)
        if canonical:
            candidates.add(canonical)
        for match in _VERSION_RE.finditer(raw):
            candidates.add(canonical_version(match.group(1)))
    return {item for item in candidates if item}


def _normalise_core(parts: tuple[int, ...]) -> tuple[int, ...]:
    values = list(parts)
    while len(values) > 2 and values[-1] == 0:
        values.pop()
    return tuple(values)


def _pad_core(parts: tuple[int, ...], size: int = 5) -> tuple[int, ...]:
    return tuple(parts) + (0,) * max(0, size - len(parts))


def _structured_version(*values: str | None) -> dict[str, object] | None:
    candidates: list[str] = []
    for value in values:
        if value:
            candidates.extend(version_candidates(value))
    for candidate in candidates:
        match = _STRUCTURED_RE.match(candidate)
        if not match:
            continue
        core = _normalise_core(tuple(int(part) for part in match.group("core").split(".")))
        suffix = (match.group("suffix") or "").lower()
        ls = _LS_RE.search(suffix)
        rc = _RC_RE.search(suffix)
        numeric = _NUMERIC_SUFFIX_RE.match(suffix)
        kind = "none"
        build: int | None = None
        if ls:
            kind, build = "ls", int(ls.group("build"))
        elif rc:
            kind, build = "rc", int(rc.group("build"))
        elif numeric:
            kind, build = "build", int(numeric.group("build"))
        elif suffix:
            kind = "other"
        return {
            "raw": candidate,
            "core": core,
            "suffix": suffix,
            "suffix_kind": kind,
            "suffix_build": build,
        }
    return None


def _same_release(installed: dict[str, object], upstream: dict[str, object]) -> bool:
    if _pad_core(installed["core"]) != _pad_core(upstream["core"]):
        return False
    installed_kind = installed["suffix_kind"]
    upstream_kind = upstream["suffix_kind"]
    installed_build = installed["suffix_build"]
    upstream_build = upstream["suffix_build"]
    if installed_kind == upstream_kind == "ls":
        return installed_build == upstream_build
    if installed_kind == upstream_kind == "rc":
        return installed_build == upstream_build
    if upstream_kind == "none" and installed_kind in {"none", "build", "other"}:
        return True
    if installed_kind == upstream_kind == "build":
        return installed_build == upstream_build
    return installed["raw"] == upstream["raw"]


def versions_match(installed: str | None, release_name: str | None, release_tag: str | None) -> bool:
    installed_candidates = version_candidates(installed)
    release_candidates = version_candidates(release_name, release_tag)
    if installed_candidates and release_candidates and installed_candidates.intersection(release_candidates):
        return True
    old = _structured_version(installed)
    new = _structured_version(release_tag, release_name)
    return bool(old and new and _same_release(old, new))


def _comparison(installed: dict[str, object], upstream: dict[str, object]) -> int | None:
    old_core = _pad_core(installed["core"])
    new_core = _pad_core(upstream["core"])
    if new_core != old_core:
        return 1 if new_core > old_core else -1

    old_kind = installed["suffix_kind"]
    new_kind = upstream["suffix_kind"]
    old_build = installed["suffix_build"]
    new_build = upstream["suffix_build"]

    if old_kind == new_kind == "ls" and old_build is not None and new_build is not None:
        return (new_build > old_build) - (new_build < old_build)
    if old_kind == new_kind == "rc" and old_build is not None and new_build is not None:
        return (new_build > old_build) - (new_build < old_build)
    if old_kind == "rc" and new_kind == "none":
        return 1
    if old_kind == "none" and new_kind == "rc":
        return -1
    if new_kind == "none" and old_kind in {"build", "other"}:
        return 0
    if old_kind == new_kind == "build" and old_build is not None and new_build is not None:
        return (new_build > old_build) - (new_build < old_build)
    if installed["raw"] == upstream["raw"]:
        return 0
    return None


def _level(old: dict[str, object], new: dict[str, object]) -> tuple[str, str]:
    old_core = _pad_core(old["core"])
    new_core = _pad_core(new["core"])
    if new_core[0] != old_core[0]:
        return "major", "high"
    if new_core[1] != old_core[1]:
        return "minor", "medium"
    return "patch", "low"


def classify_upgrade(installed: str | None, release_name: str | None, release_tag: str | None) -> dict[str, str | bool | None]:
    """Classify an installed-to-upstream transition conservatively.

    ``available`` is true only when both sides contain comparable version data and
    the upstream version is demonstrably newer. Unknown or incomparable values are
    never promoted into the upgrade queue.
    """
    if not (installed or "").strip():
        return {"available": False, "level": "unknown", "label": "Installed version unknown", "risk": "unknown", "reason": "installed_version_unavailable"}
    if not ((release_tag or "").strip() or (release_name or "").strip()):
        return {"available": False, "level": "unknown", "label": "Upstream version unavailable", "risk": "unknown", "reason": "upstream_version_unavailable"}
    if versions_match(installed, release_name, release_tag):
        return {"available": False, "level": "current", "label": "Installed current", "risk": "none", "reason": "current"}

    old = _structured_version(installed)
    new = _structured_version(release_tag, release_name)
    if not old or not new:
        return {"available": False, "level": "unknown", "label": "Version comparison unavailable", "risk": "unknown", "reason": "comparison_unavailable"}

    comparison = _comparison(old, new)
    if comparison is None:
        return {"available": False, "level": "unknown", "label": "Version comparison unavailable", "risk": "unknown", "reason": "comparison_unavailable"}
    if comparison <= 0:
        label = "Installed current" if comparison == 0 else "Installed newer than upstream"
        reason = "current" if comparison == 0 else "installed_newer"
        return {"available": False, "level": "current", "label": label, "risk": "none", "reason": reason}

    level, risk = _level(old, new)
    return {"available": True, "level": level, "label": f"{level.title()} update", "risk": risk, "reason": "update_available"}


def classify_tracker_state(tracker: Mapping[str, object]) -> dict[str, object]:
    installed = str(tracker.get("detected_installed_version") or tracker.get("installed_version") or "").strip() or None
    release_name = str(tracker.get("current_release_name") or "").strip() or None
    release_tag = str(tracker.get("current_version") or "").strip() or None
    upgrade = classify_upgrade(installed, release_name, release_tag)

    attention: list[dict[str, str]] = []
    if str(tracker.get("last_status") or "") == "error":
        attention.append({"reason": "checker_error", "label": ATTENTION_REASON_LABELS["checker_error"], "detail": str(tracker.get("last_error") or "Upstream checker failed.")})
    if str(tracker.get("last_probe_status") or "") == "error":
        attention.append({"reason": "offline", "label": ATTENTION_REASON_LABELS["offline"], "detail": str(tracker.get("last_probe_error") or "Last service probe failed.")})
    if not (release_tag or release_name):
        attention.append({"reason": "upstream_unavailable", "label": ATTENTION_REASON_LABELS["upstream_unavailable"], "detail": "No upstream release version is currently available."})
    elif upgrade.get("reason") in {"installed_version_unavailable", "comparison_unavailable"}:
        attention.append({"reason": "comparison_unavailable", "label": ATTENTION_REASON_LABELS["comparison_unavailable"], "detail": upgrade["label"]})

    update_available = bool(upgrade["available"]) and str(tracker.get("last_status") or "") != "error"
    if not update_available and upgrade["available"]:
        upgrade = {**upgrade, "available": False, "label": "Needs attention", "risk": "unknown", "reason": "checker_error"}

    return {
        "effective_installed_version": installed,
        "version_current": upgrade.get("reason") in {"current", "installed_newer"},
        "upgrade": upgrade,
        "update_available": update_available,
        "needs_attention": bool(attention),
        "attention": attention,
        "attention_reasons": [item["reason"] for item in attention],
    }


def summarise_tracker_states(trackers: list[Mapping[str, object]]) -> dict[str, int]:
    summary = {
        "updates_available": 0,
        "needs_attention": 0,
        "checker_errors": 0,
        "offline": 0,
        "upstream_unavailable": 0,
        "comparison_unavailable": 0,
    }
    for tracker in trackers:
        state = classify_tracker_state(tracker)
        if state["update_available"]:
            summary["updates_available"] += 1
        if state["needs_attention"]:
            summary["needs_attention"] += 1
        reasons = set(state["attention_reasons"])
        for key in ("checker_errors", "offline", "upstream_unavailable", "comparison_unavailable"):
            reason = "checker_error" if key == "checker_errors" else key
            if reason in reasons:
                summary[key] += 1
    return summary
