"""Orchestrate the end-to-end LinkedIn monitor pipeline."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from apply_filters import apply_hard_filters
from config_schema import validate_profile
from dedupe_jobs import dedupe_jobs
from feedback_learning import get_user_job_status
from fetch_linkedin_jobs import LinkedInSessionAdapter, fetch_linkedin_jobs_report
from normalize_jobs import normalize_jobs
from score_jobs import score_jobs
from summarize_matches import summarize_matches


def _rejection_counts(rejected: list[tuple[Any, list[str]]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for _, reasons in rejected:
        counts.update(reasons)
    return dict(sorted(counts.items()))


def _store_run_stats(state: dict[str, Any], stats: dict[str, Any], history_limit: int) -> None:
    state["last_run_stats"] = stats
    history = state.setdefault("run_history", [])
    history.append(stats)
    del history[:-history_limit]


def run_monitor(
    profile: dict[str, Any],
    dedupe_state: dict[str, Any],
    session: LinkedInSessionAdapter,
    max_fetch_cards: int = 100,
) -> tuple[str, dict[str, Any]]:
    """Run fetch -> normalize -> filter -> lifecycle/dedupe -> score -> summarize."""
    started_at = datetime.now(timezone.utc)
    started = perf_counter()
    profile = validate_profile(profile)

    fetch_result = fetch_linkedin_jobs_report(
        profile["search_url"],
        session=session,
        max_cards=max_fetch_cards,
        check_detailed_jd=profile.get("check_detailed_jd", True),
    )
    raw_jobs = fetch_result.jobs
    normalized = normalize_jobs(
        raw_jobs,
        profile_regions=profile.get("regions", []),
        profile=profile,
    )
    filter_result = apply_hard_filters(normalized, profile)

    partial_reasons = {job.job_key: reasons for job, reasons in filter_result.rejected}
    classifications = {
        job.job_key: ("partial" if job.job_key in partial_reasons else "match")
        for job in normalized
    }
    dedupe_decisions, updated_state = dedupe_jobs(
        normalized,
        state=dedupe_state,
        dedupe_window_days=profile.get("dedupe_window_days", 14),
        classifications=classifications,
        expire_after_missing_runs=profile.get("expire_after_missing_runs", 3),
        track_missing=fetch_result.stats.collection_complete,
    )

    eligible_ids = {id(job) for job in filter_result.passed}
    if profile.get("output_mode", "matches_only") == "include_partial_matches":
        eligible_ids.update(id(job) for job, _ in filter_result.rejected)

    notify_decisions = [
        decision
        for decision in dedupe_decisions
        if id(decision.job) in eligible_ids
        and decision.status in {"new", "updated", "reactivated"}
    ]
    scored = score_jobs(
        [(decision.job, decision.status) for decision in notify_decisions],
        profile,
        feedback_state=updated_state,
    )
    decision_by_object = {id(decision.job): decision for decision in notify_decisions}
    for item in scored:
        if item.job.job_key in partial_reasons:
            item.match_status = "partial_match"
            item.mismatch_reasons = partial_reasons[item.job.job_key]
        decision = decision_by_object[id(item.job)]
        item.lifecycle_status = decision.lifecycle_status
        item.user_status = get_user_job_status(updated_state, item.job)
    scored.sort(key=lambda item: (item.match_status == "match", item.score), reverse=True)

    dedupe_counts = Counter(decision.status for decision in dedupe_decisions)
    max_items = profile.get("max_results_per_digest", 10)
    run_stats: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "duration_ms": round((perf_counter() - started) * 1000, 3),
        **fetch_result.stats.to_dict(),
        "normalized": len(normalized),
        "matched": len(filter_result.passed),
        "rejected": len(filter_result.rejected),
        "rejection_reasons": _rejection_counts(filter_result.rejected),
        "dedupe_statuses": dict(sorted(dedupe_counts.items())),
        "notified": len(scored),
        "shown": min(len(scored), max_items),
        "newly_expired": updated_state.get("last_newly_expired_count", 0),
        "lifecycle": updated_state.get("last_lifecycle_counts", {}),
    }
    _store_run_stats(updated_state, run_stats, profile.get("run_history_limit", 30))

    digest = summarize_matches(
        scored_jobs=scored,
        fetched_count=len(raw_jobs),
        rejected_count=len(filter_result.rejected),
        matched_count=len(filter_result.passed),
        max_items=max_items,
        run_stats=run_stats,
    )
    return digest, updated_state
