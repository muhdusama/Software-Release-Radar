from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from .version import APP_VERSION


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    name: str | None
    url: str | None
    published_at: str | None
    body: str | None = None


_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


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
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if exc.code == 404:
            raise GitHubError("Repository or release endpoint was not found.") from exc
        if exc.code == 403:
            raise GitHubError("GitHub API rate limit or access restriction was reached.") from exc
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
