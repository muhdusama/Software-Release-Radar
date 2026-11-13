# Integrations

Release Radar can feed other tools without any extra service. Everything on
this page is read-only and works without an LLM.

## Release sources

Each tracker reads one public upstream project.

| Source | Repository value |
|---|---|
| GitHub | `owner/repository` or a `https://github.com/...` URL |
| GitLab.com | `gitlab.com/group/project` (subgroups are allowed) or the project URL |
| Codeberg | `codeberg.org/owner/repository` or the project URL |
| Gitea.com | `gitea.com/owner/repository` or the project URL |
| Self-hosted GitLab | `gitlab:git.example.com/group/project` |
| Self-hosted Gitea or Forgejo | `gitea:git.example.com/owner/repository` (`forgejo:` is accepted) |

Notes:

- Only public projects are supported. Requests use HTTPS and carry no credentials.
- GitLab has no pre-release flag. When pre-releases are excluded, tags ending in
  `alpha`, `beta`, `rc`, `pre`, `preview`, `dev` or `nightly` are skipped.
- GitLab and Gitea list releases by date. Release Radar reports the highest
  version, so a backport published after a newer release is not shown as the latest.
- The GitHub rate-limit cooldown only pauses GitHub trackers. Trackers on other
  forges continue to be checked.
- When the Assistant compares releases, it pages back through up to 300 releases
  until it finds the installed version.

## API keys

The REST API and `/metrics` use the same keys as MCP. Create one under
**Profile > API keys** with the **Read stored data** scope and send it as:

```text
Authorization: Bearer srr_...
```

Your account permissions apply: administrators also see probe configuration.
Turning MCP access off in Settings also turns these keys off. Twenty failed key
attempts from one address within 15 minutes block that address for 15 minutes.
Requests made with an API key are recorded in the audit log.

The browser session also works, which is how the command palette searches
tracked software.

## REST API

All endpoints are `GET`, return JSON and send `Cache-Control: no-store`.

| Endpoint | Query parameters |
|---|---|
| `/api/v1/status` | none |
| `/api/v1/trackers` | `limit` (1 to 100), `after_id`, `enabled` (`true` or `false`), `tag`, `q` |
| `/api/v1/trackers/<id>` | none |
| `/api/v1/trackers/<id>/releases` | `limit`, `after_id` |
| `/api/v1/trackers/<id>/upgrade` | `release_key` (defaults to the current release) |
| `/api/v1/history` | `limit`, `after_id`, `tracker_id`, `since` (`YYYY-MM-DD`) |
| `/api/v1/upgrades` | `limit`, `after_id`, `decision_status` |

Lists return `{"items": [...], "next_after_id": <id or null>}`. Pass
`next_after_id` as `after_id` to read the next page.

Errors return `{"error": "..."}` with status 400 (invalid parameter), 401
(missing or invalid key), 403 (scope or role), 404 (not found), 429 (too many
failed key attempts) or 503 (temporarily unavailable).

```bash
curl -H "Authorization: Bearer $RADAR_KEY" https://radar.example.com/api/v1/trackers?limit=50
```

## Prometheus metrics

`/metrics` uses the Prometheus text format and the same authentication.

```yaml
scrape_configs:
  - job_name: software-release-radar
    metrics_path: /metrics
    scheme: https
    authorization:
      credentials_file: /etc/prometheus/release-radar-key
    static_configs:
      - targets: ["radar.example.com"]
```

| Metric | Meaning |
|---|---|
| `srr_build_info{version,commit}` | Running build |
| `srr_trackers{state}` | Enabled and disabled trackers |
| `srr_tracker_check_success` | 1 when the last upstream check succeeded |
| `srr_tracker_update_available` | 1 when a newer release than the installed version exists |
| `srr_tracker_last_checked_timestamp_seconds` | Time of the last upstream check |
| `srr_tracker_probe_up` | 1 when the last service probe succeeded |
| `srr_tracker_probe_latency_milliseconds` | Latency of the last service probe |
| `srr_tracker_security_advisories{worst_severity}` | Published advisories affecting the installed version |
| `srr_security_advisories_affecting` | Advisories affecting installed versions across all trackers |
| `srr_updates_available` | Trackers with a confirmed update |
| `srr_trackers_needing_attention` | Trackers with checker, probe or version-data problems |
| `srr_upgrade_decisions{status}` | Decisions for each tracker's current release |
| `srr_pending_notifications` | Detected releases not yet notified |
| `srr_github_rate_limit_cooldown_seconds` | Seconds until GitHub checks resume |

Per-tracker metrics carry `tracker_id`, `name` and `repository` labels.
Example alert: `srr_tracker_probe_up == 0` for 10 minutes.

## Maintenance calendar

Under **Profile > Maintenance calendar**, create a private link and subscribe to
it in any calendar app that accepts an ICS URL. Each upgrade decision for a
tracker's current release with a planned maintenance date, and a decision of
Review, Update or Wait, appears as an all-day event with a link to its plan.

The link is shown once and works without signing in, so treat it like a
password. Replace or revoke it from the same page. The link appears in web
server access logs, like any URL.

## Proxy sign-in (forward authentication)

Release Radar can trust a username header from an authenticating reverse proxy
such as Authelia, Authentik or oauth2-proxy.

```env
RADAR_FORWARD_AUTH_HEADER=Remote-User
RADAR_FORWARD_AUTH_TRUSTED_PROXIES=192.0.2.10
```

- The header is only trusted when the direct TCP peer is one of the listed
  addresses or ranges. It is ignored from every other address, including when
  `TRUST_PROXY_HEADERS=true` rewrites the client address.
- The header must name an existing, active Release Radar user. Users are not
  created automatically, and an unknown name is refused with HTTP 403.
- Your proxy must remove any client-supplied copy of the header and must be the
  only route to Release Radar. Do not publish the application port to other
  networks while proxy sign-in is enabled.
- The built-in sign-in page keeps working for direct access.
- List the address Release Radar actually sees for the proxy. With Docker port
  publishing this is normally the proxy host's address, but some Docker setups
  show the Docker bridge gateway instead. The web container's request log shows
  the address to use.

## Security advisories

For GitHub trackers the scheduler reads the project's published repository
security advisories at most once a day per tracker, a few trackers per cycle,
and pauses during a GitHub rate-limit cooldown.

- An advisory counts against the tracked software only when one of its patched
  versions or range bounds is a known release of that tracker. Advisories for
  other components of the same repository are shown as applying to that
  component.
- The installed version is compared with each vulnerable range. When a version
  cannot be compared the status is "Cannot compare versions", never "Not affected".
- The upgrade plan shows whether upgrading to the target release fixes each
  advisory. The dashboard and queue show a chip with the count and worst
  severity.
- GitLab, Codeberg, Gitea and Forgejo trackers have no advisory source yet.

