# Company Career-Page Mode

Use `source_mode: career_pages` for recurring searches on named employers' public career sites.

## Minimum profile

```yaml
source_mode: career_pages
career_pages:
  - company: TD
    url: https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers
  - company: CIBC
    url: https://cibc.wd3.myworkdayjobs.com/search
  - company: Scotiabank
    url: https://jobs.scotiabank.com/search/
  - company: BMO
    url: https://jobs.bmo.com/ca/en/search-results
  - company: RBC
    url: https://jobs.rbc.com/ca/en/search-results
target_roles:
  - marketing manager
  - digital marketing
regions:
  - greater toronto area
```

Defaults intentionally differ from LinkedIn onboarding:

- Allow all work modes.
- Set `check_detailed_jd=false` unless the user asks for salary or JD keyword checks. Supplying a salary requirement or JD keyword rule enables it automatically when the field is otherwise omitted.
- Match target-role phrases or the same role words in a different order.
- Reuse the normal region aliases/fuzzy matching, lifecycle, feedback, dedupe, and run statistics.

When banks need different titles or JD conditions, store each bank as an independent task rather than combining every page in this example. A task may search several `target_roles`; split it only when those titles require different hard JD rules.

## Built-in Canadian bank paths

The built-in dispatcher supports these public entry types:

- TD and CIBC public `myworkdayjobs.com` pages.
- BMO's public Workday `External` page, including pasted `timeType`, `Country`, and other facet IDs.
- Scotiabank `jobs.scotiabank.com/search/` result pages.
- BMO and RBC `.../ca/en/search-results` pages.

For all five banks, replace the pasted URL's `q` or `keywords` value with each configured target title while preserving other query constraints. Filter titles before returning summaries, cap broad result scans, and let the normal GTA/fuzzy-region filter run before any optional JD request.

For public Workday URLs, `WorkdayCareerSession` discovers the tenant, site, and locale from the supplied page. It queries the public external-career search endpoint, paginates results, preserves facet IDs from the URL, uses the requisition ID as identity, and fetches JobPosting/JD detail only when enabled and selected by the normal detail plan.

BMO exposes both Workday and Phenom-branded entry pages. Both built-in readers assign BMO requisition IDs to the same `bank/bmo` identity scope, so configuring both links does not produce duplicate notifications for the same Job ID.

Keep Job IDs namespaced by career site because different employers may reuse the same requisition value. Record configured/succeeded/failed page counts and per-page errors. Do not advance missing/expired lifecycle state after a truncated or partially failed multi-page run.

## Other career platforms

Provide a runtime adapter implementing:

```python
collect_career_job_summaries(page, max_cards, target_roles)
extract_job_details(reference, check_detailed_jd)  # optional when JD checks are off
```

Each summary should expose `title`, `company`, `location_text`, `job_url`, and preferably `job_id`; it may also expose `work_mode_text`, `posted_at_text`, `salary_text`, and a detail reference.

## Limitations

- Career pages do not provide LinkedIn repost or apply-click signals.
- Some sites expose no work mode, salary, or reliable posting age on result cards.
- Public page markup and endpoints can change. Report a page failure; do not guess results. Unknown hosts still require a runtime adapter.
- Never bypass login, access controls, bot challenges, or rate limits.
