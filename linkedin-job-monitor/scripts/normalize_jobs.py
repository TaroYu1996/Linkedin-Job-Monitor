"""Normalize raw LinkedIn data into a stable internal job schema."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

from config_schema import normalize_location_type
from fetch_linkedin_jobs import RawLinkedInJob


@dataclass
class NormalizedJob:
    job_key: str
    linkedin_job_id: str | None
    job_url: str
    title: str
    company: str
    location_text: str
    normalized_region: str
    location_type: str
    salary_text: str | None
    salary_min_cad: int | None
    salary_max_cad: int | None
    salary_period: str | None
    posted_at_text: str | None
    seniority_hint: str | None
    jd_text: str
    is_reposted: bool | None
    apply_click_count: int | None
    apply_click_count_is_lower_bound: bool


_ANNUAL_HINTS = ("year", "yr", "annual", "annually")
_REPOST_MARKERS = ("reposted", "重新发布", "再次发布")


def _clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def _parse_salary_cad(salary_text: str | None) -> tuple[int | None, int | None, str | None]:
    if not salary_text:
        return None, None, None

    raw = salary_text.lower().replace(",", "")
    amounts = [int(x) for x in re.findall(r"\$?\s*(\d{2,6})", raw)]
    if not amounts:
        return None, None, None

    period = "year" if any(token in raw for token in _ANNUAL_HINTS) else None
    if period is None and any(token in raw for token in ("hour", "hr", "/h")):
        period = "hour"

    if len(amounts) == 1:
        return amounts[0], amounts[0], period
    return min(amounts), max(amounts), period


def _normalize_region(location_text: str, regions: Iterable[str]) -> str:
    loc = _clean_text(location_text).lower()
    for region in regions:
        token = _clean_text(region).lower()
        if token and token in loc:
            return token
    return "unknown"


def _derive_location_type(raw: RawLinkedInJob) -> str:
    if raw.work_mode_text:
        return normalize_location_type(raw.work_mode_text)

    loc = raw.location_text.lower()
    if "remote" in loc:
        return "remote"
    if "hybrid" in loc:
        return "hybrid"
    if "on-site" in loc or "onsite" in loc:
        return "onsite"
    return "unknown"


def _build_fallback_id(title: str, company: str, location: str) -> str:
    seed = f"{title.lower()}|{company.lower()}|{location.lower()}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _parse_card_activity(raw: RawLinkedInJob) -> tuple[bool | None, int | None, bool]:
    metadata = " ".join(
        text for text in (raw.posted_at_text, raw.apply_click_count_text) if text
    ).lower()
    is_reposted = raw.is_reposted
    if is_reposted is None and any(marker in metadata for marker in _REPOST_MARKERS):
        is_reposted = True

    # LinkedIn commonly renders phrases such as "37 people clicked apply" and
    # "100+ applicants". Keep the plus sign as an explicit lower-bound flag.
    count_match = re.search(
        r"(\d[\d,]*)\s*(\+)?\s*(?:people\s+clicked\s+apply|applicants?|人(?:点击了)?申请)",
        metadata,
    )
    if not count_match:
        return is_reposted, None, False
    return is_reposted, int(count_match.group(1).replace(",", "")), bool(count_match.group(2))


def normalize_jobs(raw_jobs: list[RawLinkedInJob], profile_regions: list[str]) -> list[NormalizedJob]:
    normalized: list[NormalizedJob] = []
    for raw in raw_jobs:
        salary_min, salary_max, salary_period = _parse_salary_cad(raw.salary_text)
        title = _clean_text(raw.title)
        company = _clean_text(raw.company)
        location_text = _clean_text(raw.location_text)
        region = _normalize_region(location_text, profile_regions)
        location_type = _derive_location_type(raw)
        fallback_id = _build_fallback_id(title, company, location_text)
        is_reposted, apply_click_count, count_is_lower_bound = _parse_card_activity(raw)

        normalized.append(
            NormalizedJob(
                job_key=raw.job_id or fallback_id,
                linkedin_job_id=raw.job_id,
                job_url=raw.job_url.strip(),
                title=title,
                company=company,
                location_text=location_text,
                normalized_region=region,
                location_type=location_type,
                salary_text=raw.salary_text,
                salary_min_cad=salary_min,
                salary_max_cad=salary_max,
                salary_period=salary_period,
                posted_at_text=raw.posted_at_text,
                seniority_hint=None,
                jd_text=_clean_text(raw.jd_text),
                is_reposted=is_reposted,
                apply_click_count=apply_click_count,
                apply_click_count_is_lower_bound=count_is_lower_bound,
            )
        )

    return normalized
