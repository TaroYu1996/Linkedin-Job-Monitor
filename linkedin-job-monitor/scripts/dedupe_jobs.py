"""Deduplication and lifecycle tracking using a JSON-like state store."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from normalize_jobs import NormalizedJob


@dataclass
class DedupeDecision:
    job: NormalizedJob
    status: str  # new | seen | updated | reactivated
    dedupe_key: str
    lifecycle_status: str = "active"  # active | missing | expired


def _canonical_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower() or "https"
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, host, path, "", ""))


def _source_prefix(job: NormalizedJob) -> str:
    if job.source_mode == "career_pages" and job.source_namespace:
        return f"career::{job.source_namespace.lower()}::"
    return ""


def canonical_job_key(job: NormalizedJob) -> str:
    """Prefer source-scoped stable job ID, then canonical URL, then content."""
    prefix = _source_prefix(job)
    if job.linkedin_job_id:
        return f"{prefix}jobid::{job.linkedin_job_id.strip().lower()}"
    if job.job_url:
        return f"{prefix}url::{_canonical_url(job.job_url).lower()}"
    fallback = f"{job.title}|{job.company}|{job.location_text}".lower()
    return f"{prefix}fallback::{hashlib.sha1(fallback.encode('utf-8')).hexdigest()}"


def card_fingerprint(job: NormalizedJob) -> str:
    """Hash stable result-card fields without time-relative posting labels or JD text."""
    payload = "|".join(
        (
            job.source_namespace or "",
            job.linkedin_job_id or "",
            job.title.lower(),
            job.company.lower(),
            job.location_text.lower(),
            job.location_type,
            (job.salary_text or "").lower(),
        )
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def filter_profile_fingerprint(profile: Mapping[str, Any]) -> str:
    """Hash only settings that can change hard-filter evaluation or JD parsing."""
    fields = (
        "source_mode",
        "career_pages",
        "target_roles",
        "regions",
        "region_aliases",
        "region_fuzzy_threshold",
        "unknown_region_policy",
        "allowed_location_types",
        "minimum_salary_cad",
        "salary_required",
        "salary_hours_per_week",
        "salary_weeks_per_year",
        "check_detailed_jd",
        "seniority",
        "title_include_keywords",
        "title_exclude_keywords",
        "jd_include_keywords",
        "jd_must_have_keywords",
        "jd_exclude_keywords",
        "company_blacklist",
        "company_whitelist",
    )
    payload = {field: profile.get(field) for field in fields}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


def _legacy_keys(job: NormalizedJob) -> list[str]:
    keys: list[str] = []
    if job.job_url:
        prefix = _source_prefix(job)
        raw = f"{prefix}url::{job.job_url.strip().lower()}"
        canonical = f"{prefix}url::{_canonical_url(job.job_url).lower()}"
        keys.extend([raw, canonical, f"partial::{raw}", f"partial::{canonical}"])
    return list(dict.fromkeys(keys))


def _content_hash(job: NormalizedJob) -> str:
    payload = "|".join(
        (
            job.title.lower(),
            job.company.lower(),
            job.location_text.lower(),
            str(job.salary_min_cad or ""),
            str(job.salary_max_cad or ""),
            job.location_type,
        )
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _jd_hash(job: NormalizedJob) -> str | None:
    if not job.jd_text:
        return None
    return hashlib.sha1(job.jd_text.lower().encode("utf-8")).hexdigest()


def _parse_timestamp(raw: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def find_job_record(
    job: NormalizedJob,
    state: Mapping[str, Any],
    dedupe_window_days: int,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Find an active Job ID/URL record without mutating state."""
    key = canonical_job_key(job)
    records = state.get("records", {})
    record = records.get(key)
    if record is None:
        for legacy_key in _legacy_keys(job):
            if legacy_key in records:
                record = records[legacy_key]
                break
    if record is None:
        return key, None
    last_seen = _parse_timestamp(record.get("last_seen_at"))
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=dedupe_window_days)
    if last_seen is None or last_seen < cutoff:
        return key, None
    return key, record


def plan_detail_fetches(
    jobs: list[NormalizedJob],
    state: Mapping[str, Any],
    dedupe_window_days: int,
    jd_refresh_days: int,
    profile_hash: str,
    check_detailed_jd: bool,
    prefiltered_keys: set[str] | None = None,
    prefilter_before_jd: bool = True,
    now: datetime | None = None,
) -> list[str]:
    """Return one `fetch:*` or `skip:*` reason for each card summary."""
    current_time = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    for job in jobs:
        if prefilter_before_jd and job.job_key in (prefiltered_keys or set()):
            reasons.append("skip:card_rejected")
            continue
        if not check_detailed_jd:
            reasons.append("skip:jd_disabled")
            continue
        _, record = find_job_record(job, state, dedupe_window_days, current_time)
        if record is None:
            reasons.append("fetch:new")
            continue
        if record.get("lifecycle_status", "active") in {"missing", "expired"}:
            reasons.append("fetch:reactivated")
            continue
        if record.get("card_hash") != card_fingerprint(job):
            reasons.append("fetch:card_changed")
            continue
        last_fetched = _parse_timestamp(record.get("last_jd_fetched_at"))
        if last_fetched is None:
            reasons.append("fetch:no_jd_cache")
            continue
        if record.get("last_jd_profile_hash") != profile_hash:
            reasons.append("fetch:profile_changed")
            continue
        if jd_refresh_days > 0 and last_fetched < current_time - timedelta(days=jd_refresh_days):
            reasons.append("fetch:refresh_due")
            continue
        reasons.append("skip:seen_unchanged")
    return reasons


def restore_cached_fields(job: NormalizedJob, record: Mapping[str, Any]) -> None:
    """Restore compact JD-derived values for an unchanged job without storing the full JD."""
    snapshot = record.get("snapshot", {})
    for field in (
        "salary_text",
        "salary_min_cad",
        "salary_max_cad",
        "salary_period",
        "salary_source",
        "seniority_hint",
    ):
        if field in snapshot:
            setattr(job, field, snapshot[field])


def _snapshot(job: NormalizedJob) -> dict[str, Any]:
    return {
        "linkedin_job_id": job.linkedin_job_id,
        "title": job.title,
        "company": job.company,
        "location_text": job.location_text,
        "location_type": job.location_type,
        "normalized_region": job.normalized_region,
        "job_url": job.job_url,
        "source_namespace": job.source_namespace,
        "source_mode": job.source_mode,
        "salary_text": job.salary_text,
        "salary_min_cad": job.salary_min_cad,
        "salary_max_cad": job.salary_max_cad,
        "salary_period": job.salary_period,
        "salary_source": job.salary_source,
        "seniority_hint": job.seniority_hint,
    }


def list_job_statuses(
    state: dict,
    lifecycle_status: str | None = None,
) -> list[dict]:
    """Return persisted discovery, lifecycle, and user statuses for inspection."""
    feedback_jobs = state.get("feedback_model", {}).get("jobs", {})
    statuses: list[dict] = []
    for key, record in state.get("records", {}).items():
        lifecycle = record.get("lifecycle_status", "active")
        if lifecycle_status and lifecycle != lifecycle_status:
            continue
        statuses.append(
            {
                "dedupe_key": key,
                "discovery_status": record.get("status"),
                "lifecycle_status": lifecycle,
                "missing_runs": record.get("missing_runs", 0),
                "user_status": feedback_jobs.get(key, {}).get("user_status"),
                "first_seen_at": record.get("first_seen_at"),
                "last_seen_at": record.get("last_seen_at"),
                **record.get("snapshot", {}),
            }
        )
    return sorted(statuses, key=lambda item: item.get("last_seen_at") or "", reverse=True)


def dedupe_jobs(
    jobs: list[NormalizedJob],
    state: dict,
    dedupe_window_days: int,
    key_namespaces: dict[str, str] | None = None,
    classifications: Mapping[str, str] | None = None,
    expire_after_missing_runs: int = 3,
    track_missing: bool = True,
    rejection_reasons: Mapping[str, list[str]] | None = None,
    card_hashes: Mapping[str, str] | None = None,
    detail_fetched_keys: set[str] | None = None,
    profile_filter_hash: str | None = None,
) -> tuple[list[DedupeDecision], dict]:
    """Classify observed jobs and cautiously track missing/expired lifecycle states."""
    records = state.setdefault("records", {})
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    expiry = now - timedelta(days=dedupe_window_days)

    active_records: dict[str, dict] = {}
    for key, value in records.items():
        last_seen = _parse_timestamp(value.get("last_seen_at"))
        if last_seen is not None and last_seen >= expiry:
            active_records[key] = value

    decisions: list[DedupeDecision] = []
    observed_keys: set[str] = set()

    for job in jobs:
        key = canonical_job_key(job)
        namespace = (key_namespaces or {}).get(job.job_key)
        if namespace:
            key = f"{namespace}::{key}"

        existing = active_records.get(key)
        if existing is None:
            for legacy_key in _legacy_keys(job):
                if legacy_key in active_records:
                    existing = active_records.pop(legacy_key)
                    break

        observed_keys.add(key)
        content_hash = _content_hash(job)
        current_jd_hash = _jd_hash(job)
        classification = (classifications or {}).get(job.job_key, "match")
        current_card_hash = (card_hashes or {}).get(job.job_key) or card_fingerprint(job)

        if existing is None:
            status = "new"
            existing = {
                "first_seen_at": now_iso,
                "content_hash": content_hash,
                "content_hash_version": 2,
                "jd_hash": current_jd_hash,
                "first_classification": classification,
                "card_hash": current_card_hash,
                "card_hash_version": 1,
            }
        else:
            previous_lifecycle = existing.get("lifecycle_status", "active")
            content_changed = (
                existing.get("content_hash_version") == 2
                and existing.get("content_hash") != content_hash
            )
            previous_jd_hash = existing.get("jd_hash")
            jd_changed = bool(
                current_jd_hash
                and previous_jd_hash
                and current_jd_hash != previous_jd_hash
            )
            classification_changed = existing.get("last_classification") not in {
                None,
                classification,
            }
            if previous_lifecycle in {"missing", "expired"}:
                status = "reactivated"
            elif content_changed or jd_changed or classification_changed:
                status = "updated"
            else:
                status = "seen"
            existing["content_hash"] = content_hash
            existing["content_hash_version"] = 2
            if current_jd_hash:
                existing["jd_hash"] = current_jd_hash

        if job.job_key in (detail_fetched_keys or set()):
            existing["last_jd_fetched_at"] = now_iso
            existing["last_jd_profile_hash"] = profile_filter_hash
            existing["details_cached"] = True

        existing.update(
            {
                "last_seen_at": now_iso,
                "last_checked_at": now_iso,
                "status": status,
                "lifecycle_status": "active",
                "missing_runs": 0,
                "last_classification": classification,
                "last_rejection_reasons": list((rejection_reasons or {}).get(job.job_key, [])),
                "card_hash": current_card_hash,
                "card_hash_version": 1,
                "snapshot": _snapshot(job),
            }
        )
        existing.pop("expired_at", None)
        active_records[key] = existing
        decisions.append(
            DedupeDecision(
                job=job,
                status=status,
                dedupe_key=key,
                lifecycle_status="active",
            )
        )

    newly_expired = 0
    if track_missing:
        for key, record in active_records.items():
            if key in observed_keys:
                continue
            previous_lifecycle = record.get("lifecycle_status", "active")
            missing_runs = int(record.get("missing_runs", 0)) + 1
            lifecycle = "expired" if missing_runs >= expire_after_missing_runs else "missing"
            record["missing_runs"] = missing_runs
            record["lifecycle_status"] = lifecycle
            record["last_checked_at"] = now_iso
            if lifecycle == "expired" and previous_lifecycle != "expired":
                record["expired_at"] = now_iso
                newly_expired += 1

    lifecycle_counts = {"active": 0, "missing": 0, "expired": 0}
    for record in active_records.values():
        lifecycle = record.get("lifecycle_status", "active")
        lifecycle_counts[lifecycle] = lifecycle_counts.get(lifecycle, 0) + 1

    state["records"] = active_records
    state["last_lifecycle_counts"] = lifecycle_counts
    state["last_newly_expired_count"] = newly_expired
    return decisions, state
