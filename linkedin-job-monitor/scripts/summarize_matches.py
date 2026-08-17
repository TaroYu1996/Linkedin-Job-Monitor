"""Build a brief digest suitable for internal chat delivery."""

from __future__ import annotations

from typing import Any

from score_jobs import ScoredJob


def _salary_line(job: ScoredJob) -> str:
    j = job.job
    if j.salary_min_cad is None:
        return j.salary_text or "n/a"
    source = f"; from {j.salary_text}" if j.salary_period in {"hour", "month"} else ""
    source_location = f"; source={j.salary_source}" if j.salary_source else ""
    if j.salary_max_cad and j.salary_max_cad != j.salary_min_cad:
        return f"CAD {j.salary_min_cad:,}-{j.salary_max_cad:,}/year{source}{source_location}"
    return f"CAD {j.salary_min_cad:,}/year{source}{source_location}"


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
    run_stats: dict[str, Any] | None = None,
    source_mode: str = "linkedin",
) -> str:
    shown = scored_jobs[:max_items]
    matched = len(scored_jobs) if matched_count is None else matched_count
    source_label = "Career-page" if source_mode == "career_pages" else "LinkedIn"
    lines: list[str] = [
        f"{source_label} monitor digest: fetched={fetched_count}, matched={matched}, shown={len(shown)}, filtered_out={rejected_count}"
    ]
    if run_stats:
        lines.append(
            "Funnel: "
            f"cards={run_stats.get('cards_collected', 0)}, "
            f"attempted={run_stats.get('cards_attempted', 0)}, "
            f"parsed={run_stats.get('jobs_parsed', 0)}, "
            f"duplicates={run_stats.get('duplicate_cards_skipped', 0)}, "
            f"jd_fetched={run_stats.get('detail_fetch_succeeded', 0)}, "
            f"jd_skipped={run_stats.get('detail_fetch_skipped', 0)}, "
            f"parse_failed={run_stats.get('parse_failed', 0)}, "
            f"fetch_errors={run_stats.get('fetch_errors', 0)}, "
            f"notified={run_stats.get('notified', 0)}, "
            f"duration_ms={run_stats.get('duration_ms', 0)}"
        )
        if source_mode == "career_pages":
            lines.append(
                "Career pages: "
                f"configured={run_stats.get('pages_configured', 0)}, "
                f"succeeded={run_stats.get('pages_succeeded', 0)}, "
                f"failed={run_stats.get('pages_failed', 0)}"
            )
            page_errors = run_stats.get("page_errors", {})
            if page_errors:
                lines.append(
                    "Career page errors: "
                    + ", ".join(
                        f"{url} ({message})"
                        for url, message in list(page_errors.items())[:3]
                    )
                )
        rejection_reasons = run_stats.get("rejection_reasons", {})
        if rejection_reasons:
            reason_text = ", ".join(
                f"{reason}={count}" for reason, count in rejection_reasons.items()
            )
            lines.append(f"Filtered reasons: {reason_text}")

    if not shown:
        lines.append("No new or updated matches met your profile criteria in this run.")
        return "\n".join(lines)

    for idx, scored in enumerate(shown, start=1):
        job = scored.job
        reason = ", ".join(scored.reasons[:3]) if scored.reasons else "profile_match"
        match_label = "partial match" if scored.match_status == "partial_match" else "match"
        user_status = f" | user_status={scored.user_status}" if scored.user_status else ""
        lines.extend(
            [
                f"{idx}. [{match_label}] {job.title} — {job.company}",
                f"   {job.location_text} | {job.location_type} | {_salary_line(scored)}",
                f"   Why matched: {reason} | score={scored.score} | status={scored.dedupe_status} | lifecycle={scored.lifecycle_status}{user_status}",
                f"   Link: {job.job_url}",
            ]
        )
        if source_mode == "linkedin":
            lines.insert(-2, f"   {_activity_line(scored)}")
        elif job.posted_at_text:
            lines.insert(-2, f"   {job.posted_at_text}")
        if scored.mismatch_reasons:
            lines.append(f"   Missing or mismatched: {', '.join(scored.mismatch_reasons)}")

    return "\n".join(lines)
