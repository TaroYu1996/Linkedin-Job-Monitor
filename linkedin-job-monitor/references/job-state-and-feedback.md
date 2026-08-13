# Job State, Feedback, and Run Statistics

## Discovery and lifecycle state

- Discovery status: `new`, `seen`, `updated`, or `reactivated`.
- Lifecycle status: `active`, `missing`, or `expired`.
- Increment `missing_runs` only after a complete, error-free, non-truncated collection.
- Mark a job `expired` after `expire_after_missing_runs` consecutive complete runs without seeing it.
- Use `list_job_statuses(state)` to inspect persisted discovery, lifecycle, and user statuses.

Absence from a partial or failed collection is not evidence that a posting expired.

## Explicit feedback

Call `record_job_feedback(state, job, signal)` only after the user explicitly supplies one of:

- `liked`
- `disliked`
- `saved`
- `ignored`
- `applied`

Feedback updates bounded title-keyword, company, and location-type weights. It adjusts ranking only and never bypasses hard filters. User-facing statuses map to `interested`, `saved`, `applied`, or `ignored`.

When feedback arrives in a later conversation turn and only the Job ID or persisted dedupe key is available, call `record_feedback_by_key(state, job_id_or_key, signal)`; it learns from the saved job snapshot.

## Funnel statistics

Each successful `run_monitor` call stores:

- `last_run_stats`: the latest run.
- `run_history`: recent runs, capped by `run_history_limit`.

Statistics include collected and attempted cards, parsed jobs, parse failures, fetch errors, normalized jobs, matched/rejected jobs, rejection-reason counts, dedupe-status counts, notification count, shown count, newly expired count, lifecycle totals, and duration.
