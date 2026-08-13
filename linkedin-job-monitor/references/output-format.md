# Output Format

Digest must be brief and suitable for internal chat delivery.

## Header

- Short summary line: counts of fetched, matched, and shown jobs.

## Item template

For each job:
1. `[match|partial match] Title — Company`
2. `Location | Work mode | Salary`
3. `<posting age> | reposted/original post | <count> clicked apply`
4. `Why matched: <short reason>`
5. `Link: <job_url>`
6. For partial matches only: `Missing or mismatched: <filter reason(s)>`

## Constraints

- Respect `max_results_per_digest`.
- In `matches_only` mode, omit every job rejected by a hard filter.
- In `include_partial_matches` mode, show full matches first and label rejected jobs as partial matches; never describe them as fully qualified.
- Keep each item to a few short lines.
- Include enough detail for quick triage.
- Preserve a `+` suffix when the displayed apply-click count is a lower bound (for example, `100+`).
- Use `posting age unknown`, `repost status unknown`, or `apply clicks unavailable` when card metadata is absent; never infer these values.
- Treat “clicked apply” as LinkedIn-displayed activity, not a verified application count.
