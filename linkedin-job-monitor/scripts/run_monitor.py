"""Orchestrate the end-to-end LinkedIn monitor pipeline."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from apply_filters import FilterResult, apply_card_prefilters, apply_hard_filters
from config_schema import validate_profile
from dedupe_jobs import (
    canonical_job_key,
    card_fingerprint,
    dedupe_jobs,
    filter_profile_fingerprint,
    find_job_record,
    plan_detail_fetches,
    restore_cached_fields,
)
from feedback_learning import get_user_job_status
from fetch_career_jobs import (
    collect_career_job_candidates_report,
    resolve_career_session,
)
from fetch_linkedin_jobs import (
    collect_linkedin_job_candidates_report,
    hydrate_job_candidates,
)
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
    session: Any | None = None,
    max_fetch_cards: int = 100,
) -> tuple[str, dict[str, Any]]:
    """Run card summaries -> pre-dedupe -> selected JD fetch -> filter/dedupe/digest."""
    started_at = datetime.now(timezone.utc)
    started = perf_counter()
    profile = validate_profile(profile)

    effective_session = session
    if profile.get("source_mode") == "career_pages":
        effective_session = resolve_career_session(session)
        candidate_result = collect_career_job_candidates_report(
            profile["career_pages"],
            session=effective_session,
            target_roles=profile.get("target_roles", []),
            max_cards_per_page=max_fetch_cards,
        )
    else:
        if session is None:
            raise ValueError("LinkedIn mode requires an authenticated session adapter")
        candidate_result = collect_linkedin_job_candidates_report(
            profile["search_url"],
            session=session,
            max_cards=max_fetch_cards,
            check_detailed_jd=profile.get("check_detailed_jd", True),
        )
    candidates = candidate_result.candidates
    summary_jobs = normalize_jobs(
        [candidate.raw for candidate in candidates],
        profile_regions=profile.get("regions", []),
        profile=profile,
    )

    # Collapse duplicate result cards before any detail page is opened.
    unique_candidates = []
    unique_summary_jobs = []
    observed_card_keys: set[str] = set()
    for candidate, job in zip(candidates, summary_jobs):
        card_key = canonical_job_key(job)
        if card_key in observed_card_keys:
            candidate_result.stats.duplicate_cards_skipped += 1
            continue
        observed_card_keys.add(card_key)
        unique_candidates.append(candidate)
        unique_summary_jobs.append(job)

    prefilter_result = apply_card_prefilters(unique_summary_jobs, profile)
    prefilter_reasons = {
        job.job_key: reasons for job, reasons in prefilter_result.rejected
    }
    profile_hash = filter_profile_fingerprint(profile)
    card_hashes = {job.job_key: card_fingerprint(job) for job in unique_summary_jobs}

    if candidate_result.stats.collection_mode != "legacy_details":
        detail_plan = plan_detail_fetches(
            unique_summary_jobs,
            dedupe_state,
            dedupe_window_days=profile.get("dedupe_window_days", 14),
            jd_refresh_days=profile.get("jd_refresh_days", 7),
            profile_hash=profile_hash,
            check_detailed_jd=profile.get("check_detailed_jd", True),
            prefiltered_keys=set(prefilter_reasons),
            prefilter_before_jd=profile.get("prefilter_before_jd", True),
        )
        detail_indexes = {
            index for index, reason in enumerate(detail_plan) if reason.startswith("fetch:")
        }
    else:
        detail_plan = ["fetch:legacy_details"] * len(unique_candidates)
        detail_indexes = set()

    detail_reason_by_key = {
        job.job_key: reason for job, reason in zip(unique_summary_jobs, detail_plan)
    }
    candidate_result.stats.detail_fetch_skipped += candidate_result.stats.duplicate_cards_skipped
    hydrated_candidates = hydrate_job_candidates(
        unique_candidates,
        detail_indexes,
        session=effective_session,
        check_detailed_jd=profile.get("check_detailed_jd", True),
        stats=candidate_result.stats,
    )
    raw_jobs = [candidate.raw for candidate in hydrated_candidates]
    normalized = normalize_jobs(
        raw_jobs,
        profile_regions=profile.get("regions", []),
        profile=profile,
    )

    detail_fetched_keys = {
        job.job_key
        for candidate, job in zip(hydrated_candidates, normalized)
        if candidate.details_loaded
    }
    for job in normalized:
        if detail_reason_by_key.get(job.job_key) != "skip:seen_unchanged":
            continue
        _, record = find_job_record(
            job,
            dedupe_state,
            profile.get("dedupe_window_days", 14),
        )
        if record is not None:
            restore_cached_fields(job, record)

    passed = []
    rejected = []
    for job in normalized:
        if profile.get("prefilter_before_jd", True) and job.job_key in prefilter_reasons:
            rejected.append((job, prefilter_reasons[job.job_key]))
            continue
        if detail_reason_by_key.get(job.job_key) == "skip:seen_unchanged":
            _, record = find_job_record(
                job,
                dedupe_state,
                profile.get("dedupe_window_days", 14),
            )
            if record is not None and record.get("last_classification") == "partial":
                rejected.append((job, list(record.get("last_rejection_reasons", []))))
            else:
                passed.append(job)
            continue
        result = apply_hard_filters([job], profile)
        passed.extend(result.passed)
        rejected.extend(result.rejected)
    filter_result = FilterResult(passed=passed, rejected=rejected)

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
        track_missing=candidate_result.stats.collection_complete,
        rejection_reasons=partial_reasons,
        card_hashes=card_hashes,
        detail_fetched_keys=detail_fetched_keys,
        profile_filter_hash=profile_hash,
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
    detail_plan_counts = Counter(detail_plan)
    max_items = profile.get("max_results_per_digest", 10)
    run_stats: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "source_mode": profile.get("source_mode", "linkedin"),
        "duration_ms": round((perf_counter() - started) * 1000, 3),
        **candidate_result.stats.to_dict(),
        "dedupe_checked": len(unique_summary_jobs),
        "prefilter_rejected": len(prefilter_reasons),
        "detail_plan_reasons": dict(sorted(detail_plan_counts.items())),
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
        source_mode=profile.get("source_mode", "linkedin"),
    )
    return digest, updated_state
