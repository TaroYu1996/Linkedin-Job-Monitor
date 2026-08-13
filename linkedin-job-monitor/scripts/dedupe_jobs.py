"""Dedupe logic using a local JSON-like state store."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from normalize_jobs import NormalizedJob


@dataclass
class DedupeDecision:
    job: NormalizedJob
    status: str  # new | seen | updated
    dedupe_key: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _content_hash(job: NormalizedJob) -> str:
    payload = f"{job.title}|{job.company}|{job.location_text}|{job.salary_text or ''}|{job.jd_text}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _dedupe_key(job: NormalizedJob) -> str:
    if job.job_url:
        return f"url::{job.job_url.strip().lower()}"
    fallback = f"{job.title}|{job.company}|{job.location_text}".lower()
    return f"fallback::{hashlib.sha1(fallback.encode('utf-8')).hexdigest()}"


def dedupe_jobs(
    jobs: list[NormalizedJob],
    state: dict,
    dedupe_window_days: int,
    key_namespaces: dict[str, str] | None = None,
) -> tuple[list[DedupeDecision], dict]:
    """Return dedupe decisions and updated state."""
    records = state.setdefault("records", {})
    now = datetime.now(UTC)
    expiry = now - timedelta(days=dedupe_window_days)

    active_records = {}
    for key, value in records.items():
        try:
            last_seen = datetime.fromisoformat(value["last_seen_at"])
            if last_seen >= expiry:
                active_records[key] = value
        except Exception:
            continue

    decisions: list[DedupeDecision] = []

    for job in jobs:
        key = _dedupe_key(job)
        namespace = (key_namespaces or {}).get(job.job_key)
        if namespace:
            key = f"{namespace}::{key}"
        new_hash = _content_hash(job)
        existing = active_records.get(key)
        if existing is None:
            status = "new"
            active_records[key] = {
                "first_seen_at": _now_iso(),
                "last_seen_at": _now_iso(),
                "content_hash": new_hash,
                "status": status,
            }
        else:
            if existing.get("content_hash") == new_hash:
                status = "seen"
            else:
                status = "updated"
                existing["content_hash"] = new_hash
            existing["last_seen_at"] = _now_iso()
            existing["status"] = status

        decisions.append(DedupeDecision(job=job, status=status, dedupe_key=key))

    state["records"] = active_records
    return decisions, state
