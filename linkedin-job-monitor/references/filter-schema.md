# Filter Schema

All filtering and ranking should read from the profile object.

## Fields

- `search_url` (str, required): authenticated LinkedIn jobs search URL.
- `target_roles` (list[str], required): role families used for ranking relevance.
- `regions` (list[str], required): allowed geography labels.
- `allowed_location_types` (list[str], required): normalized values: `remote|hybrid|onsite|unknown`.
- `minimum_salary_cad` (int | null): minimum annual CAD floor.
- `salary_required` (bool): require parseable salary estimate to pass.
- `check_detailed_jd` (bool): fetch and evaluate detailed job-description text. When `false`, skip all `jd_*` filters and JD scoring. Defaults to `true`.
- `output_mode` (str): `matches_only` returns only jobs that pass every enabled hard filter; `include_partial_matches` also returns rejected jobs, clearly labeled with their mismatch reasons. Defaults to `matches_only`.
- `seniority` (list[str]): allowed normalized seniority bands.
- `title_include_keywords` (list[str]): at least one keyword recommended for title relevance.
- `title_exclude_keywords` (list[str]): disqualifying title terms.
- `jd_include_keywords` (list[str]): positive JD relevance terms.
- `jd_must_have_keywords` (list[str]): all required JD terms.
- `jd_exclude_keywords` (list[str]): disqualifying JD terms.
- `company_blacklist` (list[str]): always reject if company matches.
- `company_whitelist` (list[str]): if non-empty, only these companies pass.
- `max_results_per_digest` (int): cap output length.
- `dedupe_window_days` (int): dedupe lookback window.
- `runs_per_day` (int): scheduler hint.

## Semantics

- Hard filters execute before scoring.
- Ranking influences ordering only, never overrides hard rejections.
- Full matches appear before partial matches when partial output is enabled.
- Disabling detailed JD checks does not disable title, company, location, salary, or seniority filters.
- Empty include lists should not block matching by default.
