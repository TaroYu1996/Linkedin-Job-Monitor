# LinkedIn Job Monitor

`LinkedIn Job Monitor` is a reusable Codex skill for monitoring LinkedIn search results or specified company career pages with a **profile-driven** pipeline.

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
- batch result-card collection with Job ID dedupe before selective JD fetching
- compact derived-field caching with configurable periodic JD refresh
- lightweight company-career mode with built-in Workday, Scotiabank, BMO, and RBC readers
- preservation of Workday URL facets and cross-entry BMO Job ID dedupe
- source-scoped requisition dedupe across multiple employer pages
- a persistent task registry that separates LinkedIn searches from independently configured career-page tasks
- per-task titles, JD rules, enable/disable controls, state, and multi-task batch statistics

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
    career-page-mode.md
    task-management.md
    output-format.md
  scripts/
    config_schema.py
    collect_profile.py
    fetch_career_jobs.py
    fetch_linkedin_jobs.py
    normalize_jobs.py
    apply_filters.py
    dedupe_jobs.py
    feedback_learning.py
    monitor_tasks.py
    score_jobs.py
    summarize_matches.py
    run_monitor.py
```

---

## Quick Start

### 1) Prepare a profile or task registry

Import `scripts/config_schema.py` and `scripts/collect_profile.py` to build or update a profile object. The scripts are Python modules rather than standalone command-line programs.

For more than one search, use `scripts/monitor_tasks.py`. Each named task contains one normal profile and keeps independent dedupe/lifecycle/feedback state. `format_monitor_task_overview(...)` groups saved tasks into LinkedIn and company-career modes without fetching jobs.

- Choose `source_mode: linkedin` or `source_mode: career_pages`.
- LinkedIn requires `search_url`, `target_roles`, `regions`, and `allowed_location_types`.
- Career-page mode requires only `career_pages`, `target_roles`, and `regions`; TD, CIBC, Scotiabank, BMO, and RBC public URLs work without a custom adapter.
- Optional:
  - salary constraints
  - optional detailed-JD inspection
  - full-match-only or full-and-partial result output
  - seniority
  - title/JD keyword constraints
  - company allow/deny lists
  - digest and scheduling controls

### 2) Provide the selected source

For the built-in Canadian bank career pages, call `run_monitor(profile, state)` without a session. The dispatcher recognizes Workday, Scotiabank's result table, and BMO/RBC Phenom pages, preserves pasted URL constraints, and queries only the configured target roles.

For LinkedIn, provide an authenticated session adapter.

`scripts/fetch_linkedin_jobs.py` defines `LinkedInSessionAdapter` protocol.  
Plug in your runtime implementation (Playwright/Selenium/hosted browser session).
For the optimized path, implement both:

- `collect_job_summaries(max_cards)` to return all visible card fields in one host call without opening details
- `extract_job_details(card_ref, check_detailed_jd)` to fetch one selected JD in one host call

The monitor deduplicates summaries first, skips definitively rejected cards, and opens only new, changed, reactivated, profile-invalidated, or refresh-due jobs. The legacy `collect_job_cards()` adapter is still supported, but it cannot avoid opening an already-seen job before learning its identity.

### 3) Run the monitor pipeline

Call `run_monitor(...)` from `scripts/run_monitor.py`:

1. batch-fetch card summaries
2. collapse duplicate Job IDs and prefilter safe card-level failures
3. fetch only selected JDs
4. normalize and hard-filter
5. update lifecycle/dedupe state
6. score and summarize

The returned state includes `last_run_stats`, bounded `run_history`, lifecycle records, and the feedback model. Use `record_job_feedback(...)` or `record_feedback_by_key(...)` only for explicit user signals and `list_job_statuses(...)` to inspect current status.

Use `run_monitor_tasks(...)` to refresh selected task IDs or all enabled tasks. It preserves per-task state and records aggregate `last_batch_stats` plus `batch_history`; one task failure does not discard successful task results.

---

## Development Notes

- Filtering and ranking are profile-driven (avoid hardcoded role logic).
- Keep runtime-specific browser behavior inside the fetch layer.
- Persist the task registry and per-task runtime state externally (JSON, DB, KV, etc.).
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
