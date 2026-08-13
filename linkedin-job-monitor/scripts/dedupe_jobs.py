"""Deduplication and lifecycle tracking using a JSON-like state store."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping
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


def canonical_job_key(job: NormalizedJob) -> str:
    """Prefer LinkedIn's stable job ID, then canonical URL, then a content fallback."""
    if job.linkedin_job_id:
        return f"jobid::{job.linkedin_job_id.strip().lower()}"
    if job.job_url:
        return f"url::{_canonical_url(job.job_url).lower()}"
    fallback = f"{job.title}|{job.company}|{job.location_text}".lower()
    return f"fallback::{hashlib.sha1(fallback.encode('utf-8')).hexdigest()}"


def _legacy_keys(job: NormalizedJob) -> list[str]:
    keys: list[str] = []
    if job.job_url:
        raw = f"url::{job.job_url.strip().lower()}"
        canonical = f"url::{_canonical_url(job.job_url).lower()}"
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


def _snapshot(job: NormalizedJob) -> dict[str, str | None]:
    return {
        "linkedin_job_id": job.linkedin_job_id,
        "title": job.title,
        "company": job.company,
        "location_text": job.location_text,
        "location_type": job.location_type,
        "normalized_region": job.normalized_region,
        "job_url": job.job_url,
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

        if existing is None:
            status = "new"
            existing = {
                "first_seen_at": now_iso,
                "content_hash": content_hash,
                "content_hash_version": 2,
                "jd_hash": current_jd_hash,
                "first_classification": classification,
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

        existing.update(
            {
                "last_seen_at": now_iso,
                "last_checked_at": now_iso,
                "status": status,
                "lifecycle_status": "active",
                "missing_runs": 0,
                "last_classification": classification,
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
