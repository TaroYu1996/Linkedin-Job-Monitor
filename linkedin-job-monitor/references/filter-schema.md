# Filter Schema

All filtering and ranking should read from the profile object.

## Fields

- `source_mode` (str): `linkedin|career_pages`; defaults to `linkedin` for backward compatibility.
- `search_url` (str): authenticated LinkedIn jobs search URL; required only in LinkedIn mode.
- `career_pages` (list[str|mapping]): public HTTPS career URLs; required only in career-page mode. A mapping may include `company` and `url`.
- `target_roles` (list[str], required): role families used for ranking relevance.
- `regions` (list[str], required): allowed geography labels.
- `region_aliases` (dict[str, list[str]]): optional custom aliases for configured regions.
- `region_fuzzy_threshold` (float): fuzzy location-component threshold from `0.5` to `1`; defaults to `0.86`.
- `unknown_region_policy` (str): `reject|include`; defaults to `reject`. Use `output_mode` to show rejected unknown-region jobs as partial matches.
- `allowed_location_types` (list[str], required): normalized values: `remote|hybrid|onsite|unknown`.
- `minimum_salary_cad` (int | null): minimum annual CAD floor.
- `salary_required` (bool): require parseable salary estimate to pass.
- `salary_hours_per_week` (int): hourly annualization assumption; defaults to `40`.
- `salary_weeks_per_year` (int): hourly annualization assumption; defaults to `52`. Monthly salary uses `12` months.
- `check_detailed_jd` (bool): fetch and evaluate detailed job-description text. When `false`, skip all `jd_*` filters and JD scoring. Defaults to `true`.
- `prefilter_before_jd` (bool): skip JD fetching when card-visible region, location type, title, or company rules already prove rejection. Defaults to `true`.
- `jd_refresh_days` (int): re-fetch an unchanged saved job after this many days; defaults to `7`. Use `0` to disable periodic refresh.
- `output_mode` (str): `matches_only` returns only jobs that pass every enabled hard filter; `include_partial_matches` also returns rejected jobs, clearly labeled with their mismatch reasons. Defaults to `matches_only`.
- `seniority` (list[str]): optional normalized bands. An empty list disables seniority filtering.
- `title_include_keywords` (list[str]): at least one keyword recommended for title relevance.
- `title_exclude_keywords` (list[str]): disqualifying title terms.
- `jd_include_keywords` (list[str]): positive JD relevance terms.
- `jd_must_have_keywords` (list[str]): all required JD terms.
- `jd_exclude_keywords` (list[str]): disqualifying JD terms.
- `company_blacklist` (list[str]): always reject if company matches.
- `company_whitelist` (list[str]): if non-empty, only these companies pass.
- `max_results_per_digest` (int): cap output length.
- `dedupe_window_days` (int): dedupe lookback window.
- `expire_after_missing_runs` (int): complete absent runs before a job becomes expired.
- `run_history_limit` (int): maximum persisted funnel-stat runs.
- `feedback_learning_enabled` (bool): enable bounded ranking adjustments from explicit feedback.
- `feedback_score_weight` (float): multiplier from `0` to `5` for learned ranking adjustments.
- `runs_per_day` (int): scheduler hint.

## Semantics

- Hard filters execute before scoring.
- Ranking influences ordering only, never overrides hard rejections.
- Full matches appear before partial matches when partial output is enabled.
- Disabling detailed JD checks does not disable title, company, location, salary, or seniority filters.
- Empty include lists should not block matching by default.
- Parse salary from the card first and detailed JD second. Compare filters against annualized CAD values while preserving the original period and source.
- Batch-read result-card summaries and deduplicate by Job ID before opening details. Missing card salary or JD fields are not safe prefilter failures.
- Use built-in Greater Toronto Area municipality aliases plus profile-defined aliases and fuzzy spelling comparison.
- In career-page mode, `target_roles` is also a card-level hard filter. A phrase matches directly or when the same role words appear in another order.
- Career-page profiles default to all work modes and `check_detailed_jd=false` when that setting is omitted.
