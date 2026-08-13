"""Build a brief digest suitable for internal chat delivery."""

from __future__ import annotations

from score_jobs import ScoredJob


def _salary_line(job: ScoredJob) -> str:
    j = job.job
    if j.salary_min_cad is None:
        return j.salary_text or "n/a"
    if j.salary_max_cad and j.salary_max_cad != j.salary_min_cad:
        return f"CAD {j.salary_min_cad:,}-{j.salary_max_cad:,}"
    return f"CAD {j.salary_min_cad:,}"


def _activity_line(job: ScoredJob) -> str:
    j = job.job
    posting = j.posted_at_text or "posting age unknown"
    if j.is_reposted is None:
        repost = "repost status unknown"
    else:
        repost = "reposted" if j.is_reposted else "original post"
    if j.apply_click_count is None:
        apply_activity = "apply clicks unavailable"
    else:
        suffix = "+" if j.apply_click_count_is_lower_bound else ""
        apply_activity = f"{j.apply_click_count:,}{suffix} clicked apply"
    return f"{posting} | {repost} | {apply_activity}"


def summarize_matches(
    scored_jobs: list[ScoredJob],
    fetched_count: int,
    rejected_count: int,
    max_items: int,
    matched_count: int | None = None,
) -> str:
    shown = scored_jobs[:max_items]
    matched = len(scored_jobs) if matched_count is None else matched_count
    lines: list[str] = [
        f"LinkedIn monitor digest: fetched={fetched_count}, matched={matched}, shown={len(shown)}, filtered_out={rejected_count}"
    ]

    if not shown:
        lines.append("No new or updated matches met your profile criteria in this run.")
        return "\n".join(lines)

    for idx, scored in enumerate(shown, start=1):
        job = scored.job
        reason = ", ".join(scored.reasons[:3]) if scored.reasons else "profile_match"
        match_label = "partial match" if scored.match_status == "partial_match" else "match"
        lines.extend(
            [
                f"{idx}. [{match_label}] {job.title} — {job.company}",
                f"   {job.location_text} | {job.location_type} | {_salary_line(scored)}",
                f"   {_activity_line(scored)}",
                f"   Why matched: {reason} | score={scored.score} | status={scored.dedupe_status}",
                f"   Link: {job.job_url}",
            ]
        )
        if scored.mismatch_reasons:
            lines.append(f"   Missing or mismatched: {', '.join(scored.mismatch_reasons)}")

    return "\n".join(lines)
