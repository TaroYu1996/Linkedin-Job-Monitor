# Setup Flow

## Goal
Collect one or more named tasks for LinkedIn or specified company career pages.

## Conversational sequence

1. Confirm whether a saved task registry or legacy profile exists.
2. If tasks exist, offer a mode-separated overview before adding another. Do not rerun tasks just to list them.
3. If missing, ask for a task name and `source_mode`: `linkedin` or `career_pages`.
4. Gather only the selected mode's required fields:
   - LinkedIn: `search_url`, `target_roles`, `regions`, `allowed_location_types`.
   - Career pages: `career_pages`, `target_roles`, `regions`.
5. In career-page mode, default to all work modes, `check_detailed_jd=false`, title/region card filtering, and no salary or seniority requirements. Ask only whether the user wants a refresh frequency or optional detailed JD checks.
   - Mention the built-in TD, CIBC, Scotiabank, BMO, and RBC support when the user wants Canadian bank monitoring.
   - Accept either BMO's Workday URL or `jobs.bmo.com` URL, or both. Explain that matching BMO Job IDs are deduplicated across the two entry types.
6. In LinkedIn mode, gather optional fields (salary, keyword filters, company controls, scheduling), including:
   - Whether to inspect detailed JD text (`check_detailed_jd`, default `true`).
   - Whether the digest should contain only full matches or also partial matches (`output_mode`, default `matches_only`).
   - Custom region aliases/fuzzy threshold and how unknown locations should be handled.
   - Hourly annualization assumptions, expiration threshold, run-history limit, and feedback-learning preference.
7. Validate the profile and add it with `create_monitor_task`.
8. Persist the registry. Keep runtime state separate and keyed by `task_id`.
9. Run only the new task when the user requests a first refresh.

## Partial update flow

1. Identify the exact task ID, then ask which profile fields should change.
2. Parse only those values.
3. Merge onto existing profile with `merge_profile_update`.
4. Revalidate the nested profile and registry.
5. Persist and optionally rerun only that task.

## Existing configuration query

When the user asks what modes or tasks already exist, use `format_monitor_task_overview`. Always show separate `LinkedIn 搜索` and `单独配置的 Career 页面` groups, including disabled tasks, target titles, regions, and concise JD rules.

## Missing profile behavior

If no registry/profile exists, do not run immediately. Ask for the source mode first, then collect its minimum fields. Do not present the LinkedIn advanced questionnaire to a career-page user.
