---
name: linkedin-job-monitor
description: Set up and run profile-driven job monitoring from LinkedIn or company career pages, including built-in public Workday, Scotiabank SuccessFactors, and BMO/RBC Phenom paths; a task registry for separate LinkedIn, bank, title, and JD configurations; title and fuzzy region matching; selective JD checks; lifecycle tracking; feedback learning; statistics; deduplication; and concise digests. Use when Codex needs to configure, list, distinguish, enable, disable, update, or run job-monitor tasks; refresh employer career sites; watch multiple titles at Canadian banks; process results; record feedback; inspect statuses; troubleshoot matches; or format a digest.
---

# LinkedIn Job Monitor

Run LinkedIn searches or specified company career pages as one deterministic monitoring pipeline. Keep credentials and browser state outside the skill directory.

## Workflow

1. Inspect the saved task registry or legacy profile and runtime capabilities.
2. If the user asks what is configured, call `format_monitor_task_overview`; separate LinkedIn searches from individually configured Career pages without starting a run. Read [task-management.md](references/task-management.md).
3. If configuration is missing, first ask the user to choose `linkedin` or `career_pages`. Read [setup-flow.md](references/setup-flow.md), then collect the task name and only that mode's minimum fields. Use [first-time-conversation-template.md](references/first-time-conversation-template.md) when a ready-made Chinese or English prompt is useful.
4. If the user requests changes, update only the named task and explicitly supplied fields; preserve all other tasks and values.
5. Validate the resulting registry and nested profiles before fetching or saving. Read [filter-schema.md](references/filter-schema.md) when interpreting fields or explaining a rejection.
6. For LinkedIn mode, confirm the two result-shaping preferences when relevant:
   - Set `check_detailed_jd` to `true` to fetch and evaluate detailed JD text, or `false` to skip JD extraction, JD filters, and JD scoring.
   - Set `output_mode` to `matches_only` for fully qualified jobs only, or `include_partial_matches` to include clearly labeled partial matches and their mismatch reasons.
7. Run the selected source or task set:
   - For `linkedin`, provide an authenticated `LinkedInSessionAdapter`, then call `run_monitor(profile, dedupe_state, session)`. Prefer the two-stage adapter path.
   - For `career_pages`, call `run_monitor(profile, dedupe_state)` to use the built-in readers for public Workday, Scotiabank, BMO, and RBC URLs. Read [career-page-mode.md](references/career-page-mode.md) for supported URLs, other platforms, or optional detailed-JD behavior.
   - For multiple tasks, call `run_monitor_tasks(registry, task_state, sessions, task_ids)`. Omit `task_ids` for all enabled tasks; key LinkedIn sessions by task ID.
8. Persist returned state under the same user. Keep each task's state isolated; never store credentials in it.
9. Return the digest without inventing missing jobs, salary data, posting age, apply-click activity, match reasons, or successful scheduling. Always rank full matches before partial matches. Distinguish reposted jobs from original posts and include the displayed posting age and “clicked apply” count when the result card exposes them.

## Use the scripts

The scripts are importable Python modules, not standalone command-line programs. Add `scripts/` to `PYTHONPATH` when importing from outside that directory:

```python
from collect_profile import merge_profile_update, parse_profile_input
from feedback_learning import record_feedback_by_key, record_job_feedback
from monitor_tasks import create_monitor_task, format_monitor_task_overview, run_monitor_tasks
from run_monitor import run_monitor

profile = parse_profile_input(conversation_fields)
digest, updated_state = run_monitor(profile, dedupe_state, session)
# After the user explicitly reacts to a returned NormalizedJob:
updated_state = record_job_feedback(updated_state, job, "liked")
# Or use a Job ID from a later chat turn:
updated_state = record_feedback_by_key(updated_state, "1234567890", "applied")
```

Use the narrowest module needed when diagnosing a pipeline stage:

- `config_schema.py` and `collect_profile.py`: normalize, validate, or partially update profiles.
- `monitor_tasks.py`: create, list, group, update, enable/disable, migrate, remove, and batch-run independent tasks.
- `fetch_linkedin_jobs.py`: define the host-specific authenticated browser adapter boundary.
- `fetch_career_jobs.py`: detect Workday, Scotiabank SuccessFactors, and BMO/RBC Phenom pages; preserve URL filters; query titles; normalize requisition IDs; and define the adapter boundary for other platforms.
- `normalize_jobs.py` and `apply_filters.py`: annualize salary, match region aliases/fuzzy names, derive optional seniority, and hard-filter jobs.
- `dedupe_jobs.py`: classify discovery as `new|seen|updated|reactivated`, track `active|missing|expired`, and list saved statuses.
- `feedback_learning.py`: record explicit `liked|disliked|saved|ignored|applied` feedback and apply bounded ranking adjustments.
- `score_jobs.py`: rank only jobs that passed hard filters; feedback never overrides a rejection.
- `summarize_matches.py`: produce the final chat digest.

## Load references as needed

- Read [scoring-rules.md](references/scoring-rules.md) when tuning or explaining ranking.
- Read [dedupe-policy.md](references/dedupe-policy.md) when changing retention or resend behavior.
- Read [job-state-and-feedback.md](references/job-state-and-feedback.md) when recording feedback or interpreting lifecycle and run statistics.
- Read [output-format.md](references/output-format.md) when changing digest presentation.
- Read [career-page-mode.md](references/career-page-mode.md) when configuring employer URLs, adding a non-Workday platform, or explaining reduced career-page functionality.
- Read [task-management.md](references/task-management.md) when listing configured modes, assigning different bank/title/JD rules, migrating a legacy profile, or running more than one task.

## Guardrails

- Keep hard filters separate from ranking; a score must never override a rejection.
- Keep seniority optional. An empty `seniority` list disables seniority filtering entirely.
- Treat hourly and monthly salary values as CAD only when the displayed text identifies them as CAD or uses `$` in a Canadian search context; preserve the source period and annualization assumptions.
- Advance missing/expired lifecycle status only after a complete, error-free, non-truncated collection.
- Learn only from explicit user feedback and keep learned weights bounded and inspectable.
- Keep runtime-specific browser selectors and session behavior in the fetch adapter layer.
- Treat `runs_per_day` as a scheduler hint, not proof that a schedule was installed.
- Ask the user to authenticate through the host runtime; never request passwords, cookies, or tokens in chat.
- Respect LinkedIn terms, applicable law, rate limits, and organizational policy. Stop rather than bypass access controls or anti-bot challenges.
- If no adapter is available, validate or update the profile and clearly report that live collection was not run.
- Prefer the adapter's optional `extract_job_card_metadata(card)` hook for `posted_at_text`, `is_reposted`, and `apply_click_count_text`; these values are displayed activity signals, not verified application totals.
- Prefer the optional `extract_job_details(card, check_detailed_jd)` fast path when the runtime can return all fields in one host call; retain the selector-by-selector path as a compatibility fallback.
- Prefer `collect_job_summaries(max_cards)` over `collect_job_cards()` whenever the runtime can batch-read the result list. Each summary should include `title`, `company`, `location_text`, `job_url`, and preferably `job_id`, plus optional card fields and an opaque `card_ref`. Do not open a detail page inside this method.
- Fetch a JD only for a new, reactivated, card-changed, profile-changed, or refresh-due job. An unchanged record reuses compact derived fields and its prior classification; the full JD is never persisted.
- Treat `jd_refresh_days=0` as disabling periodic refresh. A positive value bounds staleness because a JD can change without its result card changing.
- Apply only definitive card-level filters before JD fetching. Never reject a missing salary, JD keyword, or JD-derived seniority until the selected JD has been checked.
- In `career_pages` mode, ask only for career URLs, target titles, and regions by default. Do not walk the user through LinkedIn-only salary, seniority, repost, apply-click, or session settings unless requested.
- Keep multiple titles in one task only when their hard-filter and JD rules are shared. Use separate tasks when their JD requirements differ.
- Never erase another task while updating one. Keep task dedupe, lifecycle, feedback, and run history isolated by stable `task_id`.
- Treat the pasted URL's non-keyword filters as constraints. Search each configured target title instead of reusing a stale `q` or `keywords` value from the URL.
- Access only public employer listings. Do not bypass sign-in, challenges, robots controls, or rate limits. A page failure must remain visible in `page_errors` and must not advance missing/expired lifecycle state.
