# Dedupe Policy

## Keys

1. Primary key: LinkedIn `job_id`.
2. Secondary key: canonical `job_url` without query or fragment.
3. Fallback key: normalized `title|company|location` tuple.

Migrate legacy URL keys to Job ID keys when the same observed job exposes both.

## State

Store per-key record with:
- `first_seen_at`
- `last_seen_at`
- `content_hash`
- last discovery classification (`new|seen|updated|reactivated`)
- lifecycle status (`active|missing|expired`)
- consecutive `missing_runs`
- a compact job snapshot

## Classification

- `new`: key not present within dedupe window.
- `seen`: key exists and content hash unchanged.
- `updated`: key exists and content hash changed.
- `reactivated`: a previously missing or expired job appears again.

Only advance `missing` and `expired` states after a complete collection. Use `expire_after_missing_runs` rather than treating one absent result as expired.

## Resend rules

- Do not re-notify `seen` jobs within dedupe window.
- Allow `updated` jobs to be re-notified with update marker.
- Allow `reactivated` jobs to be re-notified.
- Expire old state entries beyond retention horizon.
