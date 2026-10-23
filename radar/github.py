from __future__ import annotations

import base64
import binascii
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from .db import connect, transaction, utcnow
from .version import APP_VERSION
from .http_client import open_http


class GitHubError(RuntimeError):
    pass


class GitHubRateLimitError(GitHubError):
    """A GitHub rate limit response, with an optional provider retry time."""

    def __init__(self, message: str, retry_at: datetime | None = None, *, deferred: bool = False):
        super().__init__(message)
        self.retry_at = retry_at
        self.deferred = deferred


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    name: str | None
    url: str | None
    published_at: str | None
    body: str | None = None


_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_ORGANIZR_REPOSITORY = "causefx/organizr"
_ORGANIZR_V2_FEED_PATH = "/repos/causefx/Organizr/contents/js/version.json?ref=v2-master"
_ORGANIZR_V2_FEED_URL = "https://github.com/causefx/Organizr/blob/v2-master/js/version.json"
_ORGANIZR_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+){1,3})(?:-([0-9A-Za-z.-]+))?$")
_RATE_LIMIT_UNTIL = "github_rate_limit_until"
_RATE_LIMIT_BACKOFF = "github_rate_limit_backoff_seconds"
_MIN_RATE_LIMIT_BACKOFF_SECONDS = 60
_MAX_RATE_LIMIT_BACKOFF_SECONDS = 3600


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _setting_value(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default


def _set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, utcnow()),
    )


def shared_rate_limit_until() -> datetime | None:
    with connect() as conn:
        return _parse_utc(_setting_value(conn, _RATE_LIMIT_UNTIL))


def _persist_rate_limit(retry_at: datetime | None) -> datetime:
    now = datetime.now(timezone.utc)
    if retry_at and retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    elif retry_at:
        retry_at = retry_at.astimezone(timezone.utc)
    with transaction() as conn:
        # Acquire the writer lock before reading settings so concurrent
        # rate-limit responses cannot
        # overwrite a longer cooldown with one based on stale state.
        conn.execute("BEGIN IMMEDIATE")
        existing = _parse_utc(_setting_value(conn, _RATE_LIMIT_UNTIL))
        try:
            backoff = int(_setting_value(conn, _RATE_LIMIT_BACKOFF, str(_MIN_RATE_LIMIT_BACKOFF_SECONDS)))
        except ValueError:
            backoff = _MIN_RATE_LIMIT_BACKOFF_SECONDS
        backoff = max(_MIN_RATE_LIMIT_BACKOFF_SECONDS, min(backoff, _MAX_RATE_LIMIT_BACKOFF_SECONDS))
        if retry_at is None or retry_at <= now:
            retry_at = now + timedelta(seconds=backoff)
        if existing and existing > retry_at:
            retry_at = existing
        retry_value = retry_at.replace(microsecond=0).isoformat()
        _set_setting(conn, _RATE_LIMIT_UNTIL, retry_value)
        _set_setting(conn, _RATE_LIMIT_BACKOFF, str(min(backoff * 2, _MAX_RATE_LIMIT_BACKOFF_SECONDS)))
    return retry_at


def _record_successful_request() -> None:
    """Reset fallback only when no newer provider cooldown is in force."""
    now = datetime.now(timezone.utc)
    with transaction() as conn:
        observed_until = _setting_value(conn, _RATE_LIMIT_UNTIL)
        existing = _parse_utc(observed_until)
        if existing and existing > now:
            return
        if not existing and _setting_value(conn, _RATE_LIMIT_BACKOFF, str(_MIN_RATE_LIMIT_BACKOFF_SECONDS)) == str(_MIN_RATE_LIMIT_BACKOFF_SECONDS):
            return
        cleared = conn.execute(
            "UPDATE settings SET value = '', updated_at = ? WHERE key = ? AND value = ?",
            (utcnow(), _RATE_LIMIT_UNTIL, observed_until),
        )
        if cleared.rowcount:
            _set_setting(conn, _RATE_LIMIT_BACKOFF, str(_MIN_RATE_LIMIT_BACKOFF_SECONDS))


def _header_value(headers, name: str) -> str:
    try:
        return str(headers.get(name) or "").strip()
    except AttributeError:
        return ""


def _rate_limit_retry_at(headers, *, now: datetime | None = None) -> datetime | None:
    """Read GitHub's retry headers defensively, retaining the latest deadline."""
    now = now or datetime.now(timezone.utc)
    candidates: list[datetime] = []
    retry_after = _header_value(headers, "Retry-After")
    if retry_after:
        try:
            seconds = int(retry_after)
        except ValueError:
            try:
                parsed = parsedate_to_datetime(retry_after)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                candidates.append(parsed.astimezone(timezone.utc))
            except (TypeError, ValueError, IndexError, OverflowError):
                pass
        else:
            if seconds >= 0:
                try:
                    candidates.append(now + timedelta(seconds=seconds))
                except OverflowError:
                    pass
    reset = _header_value(headers, "X-RateLimit-Reset")
    if reset:
        try:
            candidate = datetime.fromtimestamp(int(reset), tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            pass
        else:
            candidates.append(candidate)
    future = [candidate for candidate in candidates if candidate > now]
    return max(future) if future else None


def _is_rate_limit_response(code: int, headers, detail: str) -> bool:
    if code == 429:
        return True
    if code != 403:
        return False
    if _header_value(headers, "X-RateLimit-Remaining") == "0":
        return True
    message = detail.casefold()
    return "rate limit" in message or "abuse detection" in message


def _organizr_version_key(version: str):
    match = _ORGANIZR_VERSION_RE.fullmatch(version.strip())
    if not match:
        return None
    numbers = tuple(int(part) for part in match.group(1).split("."))
    padded = numbers + (0,) * (4 - len(numbers))
    prerelease = match.group(2) or ""
    identifiers = tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in prerelease.split(".") if part
    )
    return padded, 1 if not prerelease else 0, identifiers


def _organizr_release_body(entry: dict) -> str | None:
    sections: list[str] = []
    for label, key in (("New", "new"), ("Fixed", "fixed"), ("Notes", "notes")):
        value = str(entry.get(key) or "").strip()
        if not value:
            continue
        lines = [item.strip() for item in value.split("|") if item.strip()]
        if lines:
            sections.append(f"{label}:\n" + "\n".join(f"- {item}" for item in lines))
    body = "\n\n".join(sections).strip()
    if len(body) > 120_000:
        body = body[:120_000] + "\n\n[Release notes truncated by Software Release Radar.]"
    return body or None


def _organizr_v2_releases(include_prereleases: bool, limit: int) -> list[ReleaseInfo]:
    """Read Organizr v2's maintained version feed rather than its legacy releases."""
    payload = _github_get(_ORGANIZR_V2_FEED_PATH)
    if not isinstance(payload, dict) or str(payload.get("encoding") or "").casefold() != "base64":
        raise GitHubError("Organizr's v2 version feed was unavailable.")
    try:
        raw = base64.b64decode("".join(str(payload.get("content") or "").split()), validate=True)
        entries = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubError("Organizr's v2 version feed was unreadable.") from exc
    if not isinstance(entries, dict):
        raise GitHubError("Organizr's v2 version feed was invalid.")
    releases: list[tuple[tuple, ReleaseInfo]] = []
    for version, entry in entries.items():
        version = str(version).strip()
        key = _organizr_version_key(version)
        if key is None or (not include_prereleases and key[1] == 0) or not isinstance(entry, dict):
            continue
        name = str(entry.get("title") or "").strip() or version
        releases.append((key, ReleaseInfo(
            version=version,
            name=name,
            url=_ORGANIZR_V2_FEED_URL,
            published_at=str(entry.get("date") or "").strip() or None,
            body=_organizr_release_body(entry),
        )))
    releases.sort(key=lambda item: item[0], reverse=True)
    return [release for _, release in releases[:max(1, min(int(limit), 50))]]


def normalise_repository(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urllib.parse.urlparse(value)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            raise ValueError("Repository URL must be hosted on github.com.")
        value = parsed.path.strip("/")
    value = value.removesuffix(".git").strip("/")
    parts = value.split("/")
    if len(parts) >= 2:
        value = "/".join(parts[:2])
    if not _REPOSITORY_RE.fullmatch(value):
        raise ValueError("GitHub repository must use owner/repository format.")
    return value


def _github_get(path: str):
    cooldown = shared_rate_limit_until()
    if cooldown and cooldown > datetime.now(timezone.utc):
        raise GitHubRateLimitError(
            "GitHub API rate limit recovery is scheduled.", cooldown, deferred=True,
        )
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Software-Release-Radar/{APP_VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with open_http(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        _record_successful_request()
        return payload
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if _is_rate_limit_response(exc.code, exc.headers, detail):
            retry_at = _persist_rate_limit(_rate_limit_retry_at(exc.headers))
            raise GitHubRateLimitError(
                "GitHub API rate limit was reached.",
                retry_at,
            ) from exc
        if exc.code == 404:
            raise GitHubError("Repository or release endpoint was not found.") from exc
        if exc.code == 403:
            raise GitHubError("GitHub API access was denied.") from exc
        raise GitHubError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GitHubError(f"Could not reach GitHub: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GitHubError("GitHub returned an unreadable response.") from exc


def _release_from_payload(payload: dict) -> ReleaseInfo:
    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        raise GitHubError("GitHub release did not include a tag name.")
    name = str(payload.get("name") or "").strip() or tag
    body = str(payload.get("body") or "").strip() or None
    if body and len(body) > 120_000:
        body = body[:120_000] + "\n\n[Release notes truncated by Software Release Radar.]"
    return ReleaseInfo(
        version=tag,
        name=name,
        url=str(payload.get("html_url") or "").strip() or None,
        published_at=str(payload.get("published_at") or payload.get("created_at") or "").strip() or None,
        body=body,
    )


def get_latest(repository: str, strategy: str = "release", include_prereleases: bool = False) -> ReleaseInfo:
    repository = normalise_repository(repository)
    if repository.casefold() == _ORGANIZR_REPOSITORY and strategy == "release":
        releases = _organizr_v2_releases(include_prereleases, 1)
        if not releases:
            raise GitHubError("Organizr's v2 version feed did not include a published release.")
        return releases[0]
    owner, repo = repository.split("/", 1)
    encoded = f"/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"

    if strategy == "tag":
        payload = _github_get(f"/repos{encoded}/tags?per_page=1")
        if not isinstance(payload, list) or not payload:
            raise GitHubError("Repository does not have any tags.")
        tag = str(payload[0].get("name") or "").strip()
        if not tag:
            raise GitHubError("GitHub tag response did not include a name.")
        return ReleaseInfo(
            version=tag,
            name=tag,
            url=f"https://github.com/{repository}/releases/tag/{urllib.parse.quote(tag, safe='')}",
            published_at=None,
            body=None,
        )

    if strategy != "release":
        raise ValueError("Unknown GitHub tracking strategy.")

    if not include_prereleases:
        payload = _github_get(f"/repos{encoded}/releases/latest")
        return _release_from_payload(payload)

    payload = _github_get(f"/repos{encoded}/releases?per_page=20")
    if not isinstance(payload, list):
        raise GitHubError("GitHub returned an unexpected release response.")
    for candidate in payload:
        if not candidate.get("draft"):
            return _release_from_payload(candidate)
    raise GitHubError("Repository has no published releases.")


def get_recent_releases(repository: str, include_prereleases: bool = False, limit: int = 20) -> list[ReleaseInfo]:
    """Return recent non-draft GitHub releases, newest first."""
    repository = normalise_repository(repository)
    if repository.casefold() == _ORGANIZR_REPOSITORY:
        return _organizr_v2_releases(include_prereleases, limit)
    owner, repo = repository.split("/", 1)
    encoded = f"/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"
    limit = max(1, min(int(limit), 50))
    payload = _github_get(f"/repos{encoded}/releases?per_page={limit}")
    if not isinstance(payload, list):
        raise GitHubError("GitHub returned an unexpected release-history response.")
    releases: list[ReleaseInfo] = []
    for candidate in payload:
        if candidate.get("draft"):
            continue
        if candidate.get("prerelease") and not include_prereleases:
            continue
        try:
            releases.append(_release_from_payload(candidate))
        except GitHubError:
            continue
    return releases
