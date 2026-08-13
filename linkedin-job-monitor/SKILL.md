---
name: linkedin-job-monitor
description: Set up and run profile-driven LinkedIn job monitoring, including conversational preference collection, authenticated result collection through a user-provided session adapter, salary annualization, fuzzy region matching, deterministic filtering and ranking, job lifecycle tracking, feedback learning, run statistics, deduplication, and concise chat digests. Use when Codex needs to create or update a job-search profile, process LinkedIn job results, record job feedback, inspect job statuses, run a recurring monitor, troubleshoot match results, or format a new-and-updated-jobs digest.
---

# LinkedIn Job Monitor

Run a LinkedIn job search as a deterministic pipeline. Keep credentials and browser state outside the skill directory.

## Workflow

1. Inspect the available profile and runtime capabilities. Do not claim to fetch live jobs unless an authenticated `LinkedInSessionAdapter` is available.
2. If the profile is missing, read [setup-flow.md](references/setup-flow.md) and collect only the four required fields first. Use [first-time-conversation-template.md](references/first-time-conversation-template.md) only when a ready-made Chinese or English prompt is useful.
3. If the user requests changes, merge only explicitly supplied fields with `merge_profile_update`; preserve all other values.
4. Validate the resulting mapping with `validate_profile` before fetching or saving it. Read [filter-schema.md](references/filter-schema.md) when interpreting fields or explaining a rejection.
5. Confirm the two result-shaping preferences when relevant:
   - Set `check_detailed_jd` to `true` to fetch and evaluate detailed JD text, or `false` to skip JD extraction, JD filters, and JD scoring.
   - Set `output_mode` to `matches_only` for fully qualified jobs only, or `include_partial_matches` to include clearly labeled partial matches and their mismatch reasons.
6. Provide a runtime-owned authenticated session implementing `LinkedInSessionAdapter`, then call `run_monitor(profile, dedupe_state, session)`. The orchestrator performs fetch, normalize, hard-filter, lifecycle/deduplicate, score, and summarize in that order.
7. Persist the returned state under the same user and search context. It contains dedupe records, lifecycle statuses, explicit feedback, `last_run_stats`, and bounded `run_history`; never store credentials in it.
8. Return the digest without inventing missing jobs, salary data, posting age, apply-click activity, match reasons, or successful scheduling. Always rank full matches before partial matches. Distinguish reposted jobs from original posts and include the displayed posting age and “clicked apply” count when the result card exposes them.

## Use the scripts

The scripts are importable Python modules, not standalone command-line programs. Add `scripts/` to `PYTHONPATH` when importing from outside that directory:

```python
from collect_profile import merge_profile_update, parse_profile_input
from feedback_learning import record_feedback_by_key, record_job_feedback
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
- `fetch_linkedin_jobs.py`: define the host-specific authenticated browser adapter boundary.
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
