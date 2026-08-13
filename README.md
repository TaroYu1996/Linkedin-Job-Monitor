# LinkedIn Job Monitor

`LinkedIn Job Monitor` is a reusable Codex skill for monitoring LinkedIn job search results with a **profile-driven** pipeline.

The main skill is:

- `linkedin-job-monitor/`

It supports:

- authenticated LinkedIn job search fetching
- deterministic normalization and filtering
- deduplication against prior runs
- ranking/scoring by profile preferences
- concise internal chat digest output
- posting age, repost status, and displayed apply-click activity when available on result cards
- hourly/monthly CAD salary annualization from cards or detailed JDs
- Greater Toronto Area aliases plus configurable fuzzy region matching
- Job ID-first deduplication and active/missing/expired lifecycle tracking
- bounded learning from explicit user feedback
- per-run funnel statistics and rejection-reason counts

---

## Repository Structure

```text
linkedin-job-monitor/
  SKILL.md
  agents/openai.yaml
  references/
    setup-flow.md
    first-time-conversation-template.md
    filter-schema.md
    scoring-rules.md
    dedupe-policy.md
    job-state-and-feedback.md
    output-format.md
  scripts/
    config_schema.py
    collect_profile.py
    fetch_linkedin_jobs.py
    normalize_jobs.py
    apply_filters.py
    dedupe_jobs.py
    feedback_learning.py
    score_jobs.py
    summarize_matches.py
    run_monitor.py
```

---

## Quick Start

### 1) Prepare a profile

Import `scripts/config_schema.py` and `scripts/collect_profile.py` to build or update a profile object. The scripts are Python modules rather than standalone command-line programs.

- Required:
  - `search_url`
  - `target_roles`
  - `regions`
  - `allowed_location_types`
- Optional:
  - salary constraints
  - optional detailed-JD inspection
  - full-match-only or full-and-partial result output
  - seniority
  - title/JD keyword constraints
  - company allow/deny lists
  - digest and scheduling controls

### 2) Provide an authenticated LinkedIn session adapter

`scripts/fetch_linkedin_jobs.py` defines `LinkedInSessionAdapter` protocol.  
Plug in your runtime implementation (Playwright/Selenium/hosted browser session).
Implement the optional `extract_job_details(...)` hook to return all fields in one host call and avoid repeated selector round trips.

### 3) Run the monitor pipeline

Call `run_monitor(...)` from `scripts/run_monitor.py`:

1. fetch
2. normalize
3. filter
4. lifecycle and dedupe
5. score
6. summarize

The returned state includes `last_run_stats`, bounded `run_history`, lifecycle records, and the feedback model. Use `record_job_feedback(...)` or `record_feedback_by_key(...)` only for explicit user signals and `list_job_statuses(...)` to inspect current status.

---

## Development Notes

- Filtering and ranking are profile-driven (avoid hardcoded role logic).
- Keep runtime-specific browser behavior inside the fetch layer.
- Persist profile state and dedupe state externally (JSON, DB, KV, etc.).
- For user testing, use the bilingual first-time chat script in `linkedin-job-monitor/references/first-time-conversation-template.md`.

---

## Validation

You can run basic script validation with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=linkedin-job-monitor/scripts python -m unittest discover -s linkedin-job-monitor/tests -v
python /opt/codex/skills/.system/skill-creator/scripts/quick_validate.py linkedin-job-monitor
```

The code supports Python 3.9–3.13 and uses only the standard library. GitHub Actions verifies every supported version.

---

## Legal & Compliance Notes

- This project is not affiliated with LinkedIn.
- Ensure usage complies with LinkedIn Terms of Service, local law, and your organization’s policies.
- Do not commit sensitive personal data, cookies, tokens, or private profile identifiers.

---

## License

This repository is licensed under the MIT License. See [LICENSE](./LICENSE).
