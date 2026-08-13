# Scoring Rules

Use weighted additive scoring driven by profile fields.

## Recommended dimensions

- Target role relevance (title/JD overlap with `target_roles`).
- Title include keyword hits.
- JD include keyword hits.
- Preferred location type alignment (e.g., remote/hybrid preferences).
- Salary strength vs `minimum_salary_cad` (if salary parseable).
- Seniority fit.
- Bounded explicit-feedback adjustment for title terms, company, and location type.

## Guidance

- Keep scoring deterministic.
- Emit concise reason tags for each score contribution.
- Tune weights through config constants (not user-specific hardcoding).
- Use ranking only among jobs that passed filters.
- Keep feedback weights inspectable and bounded. Feedback never overrides hard filters.
