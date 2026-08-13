# Setup Flow

## Goal
Collect a reusable profile for recurring LinkedIn job monitoring and allow partial updates later.

## Conversational sequence

1. Confirm whether a saved profile exists.
2. If missing, gather required fields:
   - `search_url`
   - `target_roles`
   - `regions`
   - `allowed_location_types`
3. Gather optional fields (salary, keyword filters, company controls, scheduling), including:
   - Whether to inspect detailed JD text (`check_detailed_jd`, default `true`).
   - Whether the digest should contain only full matches or also partial matches (`output_mode`, default `matches_only`).
4. Validate and normalize profile via `scripts/config_schema.py`.
5. Persist profile.
6. Run monitor once and return digest.

## Partial update flow

1. Ask which profile fields should change.
2. Parse only those values.
3. Merge onto existing profile with `merge_profile_update`.
4. Revalidate merged profile.
5. Persist and optionally rerun monitor.

## Missing profile behavior

If profile is missing, do not run monitor immediately. First collect minimum required fields and confirm defaults for the rest.
