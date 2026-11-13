# Notification controls

Software Release Radar separates account recovery from release-alert delivery. An email address can remain available for password reset even when update email is disabled.

## Control order

Release-alert policy is evaluated from the broadest control to the most specific:

1. **System-wide release notifications**: an administrator can pause all update alerts.
2. **Per-software preference**: each user can choose **Always notify**, **Mute**, or **Use global default** for a tracker.
3. **Personal default**: used only when the tracker is set to **Use global default**.
4. **Delivery channels**: Email and Pushover can be enabled independently.

The system-wide switch is an absolute pause. A per-software **Always notify** choice overrides the personal default, but it cannot bypass the administrator-wide pause or deliver through a disabled channel.

## Examples

| System | Software | Personal default | Email channel | Result |
|---|---|---|---|---|
| On | Use global default | On | On | Email is sent |
| On | Use global default | Off | On | Release alert is skipped |
| On | Always notify | Off | On | Email is sent |
| On | Mute | On | On | Release alert is skipped |
| Off | Always notify | On | On | Release alert is skipped |

## No surprise backlog

A release that is muted by system, personal, software, or channel policy is written to the notification delivery ledger as deliberately skipped. Re-enabling a switch later applies to future release events and does not send every old muted release.

Failed delivery is different from deliberate skipping. Failed SMTP or Pushover delivery remains retryable because the intended policy allowed the alert but the channel could not complete it.

## Delivery, retries and upgrades

The scheduler dispatches every pending alert each cycle, oldest first, up to 50 per cycle. Each delivery (user and channel) is isolated, so one failure never stops the others.

- A failed delivery is retried after 5 minutes multiplied by the attempts so far, up to 5 attempts. After that it stays failed and no longer blocks the alert.
- An alert is marked as notified once every delivery is sent, skipped, or failed with its attempts used up. This also applies when nobody has a channel enabled.
- Pending alerts older than 7 days are closed without sending. This prevents a flood after upgrading from a version that did not record delivery, or after a long outage.
- A channel that is switched off in Settings is recorded as skipped, not failed.
- Administrators see failed deliveries under **Notifications**, Recent delivery failures.
- `python -m radar.checker --notify` uses the same dispatch and reports only alerts that are settled. Alerts with a delivery still being retried stay pending.

## System channels: webhook, ntfy and Gotify

Administrators configure these under **Settings**, **Other channels**. Each is off by default and enabled separately. They deliver once per release, not once per user, and use the same system-wide switch as other channels. They follow the notification preferences of the first active administrator: **Mute** for that software skips them, **Always notify** sends them, and **Use global default** follows that administrator's personal default.

HTTPS is required for every address unless the host is local (loopback) or `ALLOW_INSECURE_INTEGRATIONS=true`. Redirects carrying credentials must stay on the same origin. Secrets are encrypted in the database and never shown after saving. Requests time out after 10 seconds. Release notes are never sent, and all text is plain and truncated.

**Webhook.** Software Release Radar sends `POST` with `Content-Type: application/json`:

```json
{
  "event": "release.detected",
  "software": "Example",
  "repository": "owner/example",
  "machine": "server-1",
  "installed_version": "1.0.0",
  "new_version": "1.1.0",
  "release_url": "https://github.com/owner/example/releases/tag/v1.1.0",
  "detected_at": "2026-11-13T01:02:03+00:00",
  "app_version": "2.14.0"
}
```

`machine`, `installed_version` and `release_url` may be `null`. An optional bearer token is sent as `Authorization: Bearer <token>`. An optional signing secret adds `X-Radar-Signature: sha256=<hex>`, the HMAC-SHA256 of the exact request body. Verify it with a constant-time comparison. Any 2xx response counts as success.

**ntfy.** Uses the JSON publish API (`POST <server>`) with the topic, title, message, a `package` tag and a click link to the release. The server defaults to `https://ntfy.sh`. Anyone who knows a public topic name can read it, so use a hard-to-guess topic or an access token.

**Gotify.** Sends `POST <server>/message` with the application token in the `X-Gotify-Key` header (never in the URL).

## Per-software controls

Open **Notifications** and use the software list to choose:

- **Use global default**: follow the personal default;
- **Always notify**: enable alerts for this software even when the personal default is off; or
- **Mute**: suppress release alerts for this software.

The bulk toolbar can apply one choice to several visible trackers. Search by software, repository, machine, or host before selecting all visible rows.

## Channels and account recovery

The Email channel switch controls release-update email only. Password-reset email uses the configured SMTP connection and the account email address independently.

Pushover requires both:

- an administrator-configured application token; and
- a user or group key saved under **Profile**.

Pushover delivery is restricted to the fixed HTTPS Pushover API endpoint. The destination cannot be changed through application settings or notification content.

## Security and auditability

Notification preference changes are CSRF-protected and written to the audit log. Delivery records contain status and error text, but not SMTP passwords, Pushover tokens, or user keys. Integration secrets remain encrypted in SQLite.
