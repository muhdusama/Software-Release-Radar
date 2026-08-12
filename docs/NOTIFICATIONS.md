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
