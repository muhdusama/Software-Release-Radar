"""Deterministic summary of the releases between an installed and a target version.

Release notes are untrusted text. Nothing here renders them as HTML: lines are
returned as plain strings for the template to escape. Classification uses
headings and keywords only, so the result is the same every time and needs no LLM.
"""
from __future__ import annotations

import re

CATEGORIES = (
    ("breaking", "Breaking changes"),
    ("migration", "Migration steps"),
    ("security", "Security fixes"),
    ("deprecation", "Deprecations"),
)

_KEYWORDS = {
    "breaking": re.compile(r"\bbreaking\b|\bbackwards?[- ]incompatible\b|\bno longer (?:supported|works?)\b|"
                           r"\bremoved support\b|\bdrops? support\b|^\w+(?:\([^)]*\))?!:", re.IGNORECASE),
    # In body lines "migration" alone is too broad (Gitea, for example, tags its repository
    # import feature "(migrations)"), so require upgrade context.
    "migration": re.compile(r"\b(?:database|db|schema|data|config(?:uration)?)\s+migrat|"
                            r"\bmigrat\w*\s+(?:is\s+|are\s+)?(?:required|needed|necessary|mandatory)\b|"
                            r"\brun\s+(?:the\s+)?(?:\w+\s+){0,2}migrat|\bmanual (?:step|action|intervention)\b|"
                            r"\bupgrade (?:notes?|guide|instructions)\b|\bbefore upgrading\b|\bschema change", re.IGNORECASE),
    "security": re.compile(r"\bsecurity\b|\bCVE-\d{4}-\d{4,}\b|\bGHSA(?:-[23456789cfghjmpqrvwx]{4}){3}\b|"
                           r"\bvulnerab|\bXSS\b|\bCSRF\b|\bRCE\b|\bSSRF\b|\binjection\b", re.IGNORECASE),
    "deprecation": re.compile(r"\bdeprecat", re.IGNORECASE),
}
# Headings are short and deliberate, so broader words are reliable there.
_HEADING_KEYWORDS = {
    "breaking": re.compile(r"breaking|incompatib", re.IGNORECASE),
    "migration": re.compile(r"migration (?:guide|notes?|steps?)|^\W*migrations?\W*$|upgrade (?:notes?|guide|instructions)|upgrading", re.IGNORECASE),
    "security": re.compile(r"security|vulnerab", re.IGNORECASE),
    "deprecation": re.compile(r"deprecat", re.IGNORECASE),
}
_ADVISORY_RE = re.compile(r"\b(CVE-\d{4}-\d{4,}|GHSA(?:-[23456789cfghjmpqrvwx]{4}){3})\b", re.IGNORECASE)
_HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s+|\*\*|__)(.+?)(?:\*\*|__)?\s*:?\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_MARKUP_RE = re.compile(r"[`*_]{1,3}|\[([^\]]*)\]\([^)]*\)|<[^>]{0,200}>")
MAX_LINES_PER_CATEGORY = 4
MAX_LINE_CHARS = 220


def _plain(line: str) -> str:
    text = _BULLET_RE.sub("", line)
    text = _MARKUP_RE.sub(lambda match: match.group(1) or "", text)
    text = " ".join(text.split())
    return text[:MAX_LINE_CHARS - 1] + "…" if len(text) > MAX_LINE_CHARS else text


def classify_notes(body: str | None) -> dict[str, list[str]]:
    """Return matching lines per category. A heading such as "Breaking changes"
    puts the bullet lines under it into that category."""
    found: dict[str, list[str]] = {key: [] for key, _ in CATEGORIES}
    section: str | None = None
    for raw in str(body or "").splitlines()[:2000]:
        if not raw.strip():
            continue
        heading = _HEADING_RE.match(raw)
        if heading and not _BULLET_RE.match(raw):
            title = heading.group(1)
            section = next((key for key, _ in CATEGORIES if _HEADING_KEYWORDS[key].search(title.strip())), None)
            continue
        text = _plain(raw)
        if len(text) < 3:
            continue
        words = text.rstrip(":").split()
        if len(words) <= 3 and (text.rstrip(":").isupper() or text.endswith(":")):
            # A short label such as "* BREAKING" or "Security:" starts a section, as Gitea writes them.
            section = next((key for key, _ in CATEGORIES if _HEADING_KEYWORDS[key].search(text.rstrip(":"))), None)
            continue
        keys = [key for key, _ in CATEGORIES if _KEYWORDS[key].search(text)]
        if section and section not in keys:
            keys.insert(0, section)
        for key in keys:
            if len(found[key]) < MAX_LINES_PER_CATEGORY and text not in found[key]:
                found[key].append(text)
    return found


def advisory_ids(body: str | None) -> list[str]:
    seen: list[str] = []
    for match in _ADVISORY_RE.finditer(str(body or "")):
        value = match.group(1).upper() if match.group(1).upper().startswith("CVE") else "GHSA" + match.group(1)[4:].lower()
        if value not in seen:
            seen.append(value)
    return seen[:20]


def digest(releases: list[dict]) -> dict[str, object]:
    """Summarise releases (newest first) for the upgrade decision page."""
    items = []
    totals = {key: 0 for key, _ in CATEGORIES}
    advisories: list[str] = []
    for release in releases:
        signals = classify_notes(release.get("body"))
        for key in totals:
            totals[key] += 1 if signals[key] else 0
        ids = advisory_ids(release.get("body"))
        advisories.extend(item for item in ids if item not in advisories)
        items.append({**release, "signals": signals, "advisories": ids,
                      "has_notes": bool(str(release.get("body") or "").strip())})
    return {"releases": items, "totals": totals, "advisories": advisories[:30],
            "labels": dict(CATEGORIES)}
