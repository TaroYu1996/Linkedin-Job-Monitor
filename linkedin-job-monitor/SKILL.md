---
name: linkedin-job-monitor
description: Set up and run profile-driven LinkedIn job monitoring, including conversational preference collection, authenticated result collection through a user-provided session adapter, deterministic filtering and ranking, seen-job deduplication, and concise chat digests. Use when Codex needs to create or update a job-search profile, process LinkedIn job results, run a recurring monitor, troubleshoot match results, or format a new-and-updated-jobs digest.
---

# LinkedIn Job Monitor

Run a LinkedIn job search as a deterministic pipeline. Keep credentials and browser state outside the skill directory.

## Workflow

1. Inspect the available profile and runtime capabilities. Do not claim to fetch live jobs unless an authenticated `LinkedInSessionAdapter` is available.
2. If the profile is missing, read [setup-flow.md](references/setup-flow.md) and collect only the four required fields first. Use [first-time-conversation-template.md](references/first-time-conversation-template.md) only when a ready-made Chinese or English prompt is useful.
3. If the user requests changes, merge only explicitly supplied fields with `merge_profile_update`; preserve all other values.
4. Validate the resulting mapping with `validate_profile` before fetching or saving it. Read [filter-schema.md](references/filter-schema.md) when interpreting fields or explaining a rejection.
5. Provide a runtime-owned authenticated session implementing `LinkedInSessionAdapter`, then call `run_monitor(profile, dedupe_state, session)`. The orchestrator performs fetch, normalize, hard-filter, deduplicate, score, and summarize in that order.
6. Persist the returned dedupe state under the same user and search context. Never persist cookies, tokens, or credentials in the profile or dedupe state.
7. Return the digest without inventing missing jobs, salary data, match reasons, or successful scheduling.

## Use the scripts

The scripts are importable Python modules, not standalone command-line programs. Add `scripts/` to `PYTHONPATH` when importing from outside that directory:

```python
from collect_profile import merge_profile_update, parse_profile_input
from run_monitor import run_monitor

profile = parse_profile_input(conversation_fields)
digest, updated_state = run_monitor(profile, dedupe_state, session)
```

Use the narrowest module needed when diagnosing a pipeline stage:

- `config_schema.py` and `collect_profile.py`: normalize, validate, or partially update profiles.
- `fetch_linkedin_jobs.py`: define the host-specific authenticated browser adapter boundary.
- `normalize_jobs.py` and `apply_filters.py`: inspect normalized fields and hard-filter rejection reasons.
- `dedupe_jobs.py`: classify jobs as `new`, `seen`, or `updated`.
- `score_jobs.py`: rank only jobs that passed hard filters.
- `summarize_matches.py`: produce the final chat digest.

## Load references as needed

- Read [scoring-rules.md](references/scoring-rules.md) when tuning or explaining ranking.
- Read [dedupe-policy.md](references/dedupe-policy.md) when changing retention or resend behavior.
- Read [output-format.md](references/output-format.md) when changing digest presentation.

## Guardrails

- Keep hard filters separate from ranking; a score must never override a rejection.
- Keep runtime-specific browser selectors and session behavior in the fetch adapter layer.
- Treat `runs_per_day` as a scheduler hint, not proof that a schedule was installed.
- Ask the user to authenticate through the host runtime; never request passwords, cookies, or tokens in chat.
- Respect LinkedIn terms, applicable law, rate limits, and organizational policy. Stop rather than bypass access controls or anti-bot challenges.
- If no adapter is available, validate or update the profile and clearly report that live collection was not run.
