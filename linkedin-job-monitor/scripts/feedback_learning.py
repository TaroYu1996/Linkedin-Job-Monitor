"""Deterministic, bounded preference learning from explicit user feedback."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from dedupe_jobs import canonical_job_key
from normalize_jobs import NormalizedJob

FEEDBACK_SIGNALS = {"liked", "disliked", "saved", "ignored", "applied"}
_SIGNAL_WEIGHTS = {
    "liked": 1.0,
    "saved": 1.5,
    "applied": 2.0,
    "disliked": -1.5,
    "ignored": -1.0,
}
_USER_STATUSES = {
    "liked": "interested",
    "saved": "saved",
    "applied": "applied",
    "disliked": "ignored",
    "ignored": "ignored",
}
_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "of",
    "in",
    "a",
    "an",
    "to",
    "job",
    "role",
    "specialist",
}


def _bounded(value: float, lower: float = -5.0, upper: float = 5.0) -> float:
    return round(max(lower, min(value, upper)), 3)


def _title_tokens(title: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9+#.-]{1,}", title.lower())
    return list(dict.fromkeys(token for token in tokens if token not in _STOPWORDS))


def _update_weight(mapping: dict[str, float], key: str, delta: float) -> None:
    if key:
        mapping[key] = _bounded(float(mapping.get(key, 0.0)) + delta)


def _record_feedback_features(
    state: dict[str, Any],
    key: str,
    signal: str,
    title: str,
    company: str,
    location_type: str,
    linkedin_job_id: str | None,
) -> dict[str, Any]:
    model = state.setdefault(
        "feedback_model",
        {
            "version": 1,
            "jobs": {},
            "keyword_weights": {},
            "company_weights": {},
            "location_type_weights": {},
            "events": [],
        },
    )
    weight = _SIGNAL_WEIGHTS[signal]
    now_iso = datetime.now(timezone.utc).isoformat()
    model.setdefault("jobs", {})[key] = {
        "signal": signal,
        "user_status": _USER_STATUSES[signal],
        "updated_at": now_iso,
        "linkedin_job_id": linkedin_job_id,
        "title": title,
        "company": company,
        "location_type": location_type,
    }
    keyword_weights = model.setdefault("keyword_weights", {})
    for token in _title_tokens(title):
        _update_weight(keyword_weights, token, weight * 0.2)
    _update_weight(model.setdefault("company_weights", {}), company.lower(), weight * 0.5)
    _update_weight(
        model.setdefault("location_type_weights", {}),
        location_type,
        weight * 0.25,
    )
    events = model.setdefault("events", [])
    events.append({"job_key": key, "signal": signal, "at": now_iso})
    del events[:-200]
    return state


def record_job_feedback(
    state: dict[str, Any],
    job: NormalizedJob,
    signal: str,
) -> dict[str, Any]:
    """Record explicit feedback and update a small, interpretable preference model."""
    normalized_signal = signal.strip().lower()
    if normalized_signal not in FEEDBACK_SIGNALS:
        supported = ", ".join(sorted(FEEDBACK_SIGNALS))
        raise ValueError(f"Unsupported feedback signal: {signal}. Expected one of: {supported}")

    key = canonical_job_key(job)
    return _record_feedback_features(
        state,
        key,
        normalized_signal,
        job.title,
        job.company,
        job.location_type,
        job.linkedin_job_id,
    )


def record_feedback_by_key(
    state: dict[str, Any],
    job_key_or_id: str,
    signal: str,
) -> dict[str, Any]:
    """Record feedback later using a persisted dedupe key or LinkedIn Job ID."""
    normalized_signal = signal.strip().lower()
    if normalized_signal not in FEEDBACK_SIGNALS:
        supported = ", ".join(sorted(FEEDBACK_SIGNALS))
        raise ValueError(f"Unsupported feedback signal: {signal}. Expected one of: {supported}")

    requested = job_key_or_id.strip()
    candidates = [requested]
    if requested.isdigit():
        candidates.insert(0, f"jobid::{requested}")
    records = state.get("records", {})
    key = next((candidate for candidate in candidates if candidate in records), None)
    if key is None:
        for candidate_key, record in records.items():
            snapshot = record.get("snapshot", {})
            if requested in {snapshot.get("linkedin_job_id"), snapshot.get("job_url")}:
                key = candidate_key
                break
    if key is None:
        raise KeyError(f"No persisted job found for: {job_key_or_id}")

    snapshot = records[key].get("snapshot", {})
    return _record_feedback_features(
        state,
        key,
        normalized_signal,
        str(snapshot.get("title") or ""),
        str(snapshot.get("company") or ""),
        str(snapshot.get("location_type") or "unknown"),
        snapshot.get("linkedin_job_id"),
    )


def feedback_adjustment(
    job: NormalizedJob,
    state: dict[str, Any] | None,
) -> tuple[float, list[str]]:
    """Return a bounded ranking adjustment; never use feedback as a hard filter."""
    model = (state or {}).get("feedback_model", {})
    if not model:
        return 0.0, []

    reasons: list[str] = []
    adjustment = 0.0
    direct = model.get("jobs", {}).get(canonical_job_key(job))
    if direct:
        direct_weight = _SIGNAL_WEIGHTS.get(direct.get("signal"), 0.0)
        adjustment += direct_weight
        if direct_weight:
            reasons.append(f"feedback_direct:{direct.get('signal')}")

    company_weight = float(model.get("company_weights", {}).get(job.company.lower(), 0.0))
    if company_weight:
        adjustment += max(-1.5, min(company_weight, 1.5))
        reasons.append("feedback_company")

    location_weight = float(
        model.get("location_type_weights", {}).get(job.location_type, 0.0)
    )
    if location_weight:
        adjustment += max(-0.5, min(location_weight, 0.5))
        reasons.append("feedback_location")

    keyword_weights = model.get("keyword_weights", {})
    token_adjustments = sorted(
        (float(keyword_weights.get(token, 0.0)) for token in _title_tokens(job.title)),
        key=abs,
        reverse=True,
    )[:5]
    if token_adjustments:
        keyword_adjustment = max(-1.5, min(sum(token_adjustments) * 0.25, 1.5))
        adjustment += keyword_adjustment
        if keyword_adjustment:
            reasons.append("feedback_title")

    return _bounded(adjustment, -3.0, 3.0), reasons


def get_user_job_status(
    state: dict[str, Any] | None,
    job: NormalizedJob,
) -> str | None:
    model = (state or {}).get("feedback_model", {})
    record = model.get("jobs", {}).get(canonical_job_key(job), {})
    return record.get("user_status")
