"""Orchestrate end-to-end LinkedIn monitor pipeline."""

from __future__ import annotations

from typing import Any

from apply_filters import apply_hard_filters
from dedupe_jobs import dedupe_jobs
from fetch_linkedin_jobs import LinkedInSessionAdapter, fetch_linkedin_jobs
from normalize_jobs import normalize_jobs
from score_jobs import score_jobs
from summarize_matches import summarize_matches


def run_monitor(
    profile: dict[str, Any],
    dedupe_state: dict[str, Any],
    session: LinkedInSessionAdapter,
    max_fetch_cards: int = 100,
) -> tuple[str, dict[str, Any]]:
    """Run fetch -> normalize -> filter -> dedupe -> score -> summarize."""
    raw_jobs = fetch_linkedin_jobs(
        profile["search_url"],
        session=session,
        max_cards=max_fetch_cards,
        check_detailed_jd=profile.get("check_detailed_jd", True),
    )
    normalized = normalize_jobs(raw_jobs, profile_regions=profile.get("regions", []))

    filter_result = apply_hard_filters(normalized, profile)

    candidates = list(filter_result.passed)
    partial_reasons: dict[str, list[str]] = {}
    if profile.get("output_mode", "matches_only") == "include_partial_matches":
        for job, reasons in filter_result.rejected:
            candidates.append(job)
            partial_reasons[job.job_key] = reasons

    dedupe_decisions, updated_state = dedupe_jobs(
        candidates,
        state=dedupe_state,
        dedupe_window_days=profile.get("dedupe_window_days", 14),
        key_namespaces={job_key: "partial" for job_key in partial_reasons},
    )

    notify_candidates = [d for d in dedupe_decisions if d.status in {"new", "updated"}]
    jobs_with_status = [(d.job, d.status) for d in notify_candidates]
    scored = score_jobs(jobs_with_status, profile)
    for item in scored:
        if item.job.job_key in partial_reasons:
            item.match_status = "partial_match"
            item.mismatch_reasons = partial_reasons[item.job.job_key]
    scored.sort(key=lambda item: (item.match_status == "match", item.score), reverse=True)

    digest = summarize_matches(
        scored_jobs=scored,
        fetched_count=len(raw_jobs),
        rejected_count=len(filter_result.rejected),
        matched_count=len(filter_result.passed),
        max_items=profile.get("max_results_per_digest", 10),
    )
    return digest, updated_state
