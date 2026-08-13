"""Normalize raw LinkedIn data into a stable internal job schema."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

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
    region_match_score: float = 0.0
    region_match_method: str | None = None
    salary_source: str | None = None


@dataclass(frozen=True)
class SalaryEstimate:
    annual_min_cad: int
    annual_max_cad: int
    source_period: str
    matched_text: str


_REPOST_MARKERS = ("reposted", "重新发布", "再次发布")
_GTA_ALIASES = (
    "gta",
    "toronto",
    "city of toronto",
    "markham",
    "mississauga",
    "brampton",
    "vaughan",
    "richmond hill",
    "oakville",
    "burlington",
    "ajax",
    "pickering",
    "whitby",
    "oshawa",
    "scarborough",
    "etobicoke",
    "north york",
    "east york",
    "york region",
    "newmarket",
    "aurora",
    "milton",
    "caledon",
    "halton hills",
    "clarington",
)
_BUILTIN_REGION_ALIASES: dict[str, tuple[str, ...]] = {
    "greater toronto area": _GTA_ALIASES,
    "greater toronto area, canada": _GTA_ALIASES,
}
_SALARY_RE = re.compile(
    r"(?P<prefix>(?:cad|c\$)\s*\$?|\$)\s*"
    r"(?P<low>\d[\d,]*(?:\.\d+)?)\s*(?P<low_k>k)?"
    r"(?:\s*(?:-|–|—|to)\s*(?:(?:cad|c\$)\s*\$?|\$)?\s*"
    r"(?P<high>\d[\d,]*(?:\.\d+)?)\s*(?P<high_k>k)?)?"
    r"(?:\s*(?:cad)?)?\s*"
    r"(?P<period>per\s+hour|an\s+hour|hourly|/\s*h(?:ou)?r|per\s+month|a\s+month|monthly|/\s*mo(?:nth)?|per\s+year|a\s+year|annually|annual|yearly|/\s*y(?:ea)?r)?",
    re.IGNORECASE,
)
_SALARY_SUFFIX_CAD_RE = re.compile(
    r"(?P<low>\d[\d,]*(?:\.\d+)?)\s*(?P<low_k>k)?"
    r"(?:\s*(?:-|–|—|to)\s*(?P<high>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<high_k>k)?)?\s*cad\s*"
    r"(?P<period>per\s+hour|an\s+hour|hourly|/\s*h(?:ou)?r|per\s+month|a\s+month|monthly|/\s*mo(?:nth)?|per\s+year|a\s+year|annually|annual|yearly|/\s*y(?:ea)?r)",
    re.IGNORECASE,
)
_JOB_ID_RE = re.compile(r"/jobs/view/(\d+)")
_SENIORITY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("executive", ("chief ", "c-level", "c suite")),
    ("vp", ("vice president", "vp ", "v.p.")),
    ("director", ("director", "head of")),
    ("manager", ("manager", "management")),
    ("lead", ("team lead", "technical lead", "lead ")),
    ("staff", ("principal", "staff ")),
    ("senior", ("senior", "sr.", "sr ")),
    ("associate", ("associate",)),
    ("entry", ("junior", "jr.", "jr ", "entry level", "entry-level")),
    ("intern", ("intern", "internship", "co-op", "coop")),
)


def _clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def _normalize_match_text(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).split())


def _amount_value(raw: str, has_k_suffix: bool) -> float:
    value = float(raw.replace(",", ""))
    return value * 1000 if has_k_suffix else value


def _period_name(raw: str | None, low: float) -> str | None:
    if raw:
        token = re.sub(r"\s+", "", raw.lower())
        if "hour" in token or token in {"/hr", "/h"}:
            return "hour"
        if "month" in token or token in {"/mo"}:
            return "month"
        if "year" in token or "annual" in token or token == "/yr":
            return "year"
    if low >= 10000:
        return "year"
    return None


def _parse_salary_cad(
    salary_text: str | None,
    hours_per_week: int = 40,
    weeks_per_year: int = 52,
) -> SalaryEstimate | None:
    """Extract the first CAD salary range and annualize hourly or monthly pay."""
    if not salary_text:
        return None

    matches = list(_SALARY_RE.finditer(salary_text))
    matches.extend(_SALARY_SUFFIX_CAD_RE.finditer(salary_text))
    matches.sort(key=lambda item: item.start())
    for match in matches:
        low = _amount_value(match.group("low"), bool(match.group("low_k")))
        high_raw = match.group("high")
        high = (
            _amount_value(high_raw, bool(match.group("high_k")))
            if high_raw
            else low
        )
        period = _period_name(match.group("period"), low)
        if period is None:
            continue
        if period == "hour":
            factor = hours_per_week * weeks_per_year
        elif period == "month":
            factor = 12
        else:
            factor = 1
        annual_low = int(round(min(low, high) * factor))
        annual_high = int(round(max(low, high) * factor))
        return SalaryEstimate(
            annual_min_cad=annual_low,
            annual_max_cad=annual_high,
            source_period=period,
            matched_text=_clean_text(match.group(0)),
        )
    return None


def _region_aliases(
    region: str,
    custom_aliases: Mapping[str, Iterable[str]],
) -> list[str]:
    canonical = _normalize_match_text(region)
    aliases = [canonical]
    aliases.extend(_BUILTIN_REGION_ALIASES.get(canonical, ()))
    for configured_region, configured_aliases in custom_aliases.items():
        if _normalize_match_text(configured_region) == canonical:
            aliases.extend(configured_aliases)
    return list(dict.fromkeys(_normalize_match_text(alias) for alias in aliases if alias))


def _prepare_regions(
    regions: Iterable[str],
    custom_aliases: Mapping[str, Iterable[str]],
) -> list[tuple[str, list[str]]]:
    return [
        (_normalize_match_text(region), _region_aliases(region, custom_aliases))
        for region in regions
    ]


def _normalize_region(
    location_text: str,
    regions: Iterable[str],
    custom_aliases: Mapping[str, Iterable[str]] | None = None,
    fuzzy_threshold: float = 0.86,
    prepared_regions: list[tuple[str, list[str]]] | None = None,
) -> tuple[str, float, str | None]:
    location = _normalize_match_text(location_text)
    components = [
        token
        for token in (
            _normalize_match_text(part)
            for part in re.split(r"[,|/]", location_text)
        )
        if token
    ]
    padded_location = f" {location} "
    prepared = prepared_regions or _prepare_regions(regions, custom_aliases or {})

    for canonical, _ in prepared:
        if f" {canonical} " in padded_location:
            return canonical, 1.0, "exact"

    for canonical, aliases in prepared:
        if any(f" {alias} " in padded_location for alias in aliases if alias != canonical):
            return canonical, 0.98, "alias"

    best_region = "unknown"
    best_score = 0.0
    for canonical, aliases in prepared:
        for alias in aliases:
            score = max(
                (SequenceMatcher(None, alias, component).ratio() for component in components),
                default=0.0,
            )
            if score > best_score:
                best_region = canonical
                best_score = score

    if best_score < fuzzy_threshold:
        return "unknown", round(best_score, 3), None
    return best_region, round(best_score, 3), "fuzzy"


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


def _linkedin_job_id(raw: RawLinkedInJob) -> str | None:
    if raw.job_id and raw.job_id.strip():
        return raw.job_id.strip()
    path = urlsplit(raw.job_url).path
    match = _JOB_ID_RE.search(path)
    return match.group(1) if match else None


def _derive_seniority(title: str, jd_text: str) -> str | None:
    title_text = f" {_normalize_match_text(title)} "
    jd_prefix = f" {_normalize_match_text(jd_text[:2000])} "
    for level, markers in _SENIORITY_PATTERNS:
        if any(marker in title_text for marker in markers):
            return level
    for level, markers in _SENIORITY_PATTERNS:
        if any(marker in jd_prefix for marker in markers):
            return level
    return None


def _parse_card_activity(raw: RawLinkedInJob) -> tuple[bool | None, int | None, bool]:
    metadata = " ".join(
        text for text in (raw.posted_at_text, raw.apply_click_count_text) if text
    ).lower()
    is_reposted = raw.is_reposted
    if is_reposted is None and any(marker in metadata for marker in _REPOST_MARKERS):
        is_reposted = True

    # Applicant totals are intentionally not treated as "clicked apply" activity.
    count_match = re.search(
        r"(\d[\d,]*)\s*(\+)?\s*(?:people\s+clicked\s+apply|人(?:点击了)?申请)",
        metadata,
    )
    if not count_match:
        return is_reposted, None, False
    return is_reposted, int(count_match.group(1).replace(",", "")), bool(count_match.group(2))


def normalize_jobs(
    raw_jobs: list[RawLinkedInJob],
    profile_regions: list[str],
    profile: Mapping[str, Any] | None = None,
) -> list[NormalizedJob]:
    settings = profile or {}
    hours_per_week = int(settings.get("salary_hours_per_week", 40))
    weeks_per_year = int(settings.get("salary_weeks_per_year", 52))
    prepared_regions = _prepare_regions(
        profile_regions,
        settings.get("region_aliases", {}),
    )
    normalized: list[NormalizedJob] = []

    for raw in raw_jobs:
        salary = _parse_salary_cad(raw.salary_text, hours_per_week, weeks_per_year)
        salary_source = "card" if salary else None
        if salary is None and raw.jd_text:
            salary = _parse_salary_cad(raw.jd_text, hours_per_week, weeks_per_year)
            salary_source = "jd" if salary else None

        title = _clean_text(raw.title)
        company = _clean_text(raw.company)
        location_text = _clean_text(raw.location_text)
        region, region_score, region_method = _normalize_region(
            location_text,
            profile_regions,
            custom_aliases=settings.get("region_aliases", {}),
            fuzzy_threshold=float(settings.get("region_fuzzy_threshold", 0.86)),
            prepared_regions=prepared_regions,
        )
        location_type = _derive_location_type(raw)
        fallback_id = _build_fallback_id(title, company, location_text)
        linkedin_job_id = _linkedin_job_id(raw)
        is_reposted, apply_click_count, count_is_lower_bound = _parse_card_activity(raw)

        normalized.append(
            NormalizedJob(
                job_key=linkedin_job_id or fallback_id,
                linkedin_job_id=linkedin_job_id,
                job_url=raw.job_url.strip(),
                title=title,
                company=company,
                location_text=location_text,
                normalized_region=region,
                location_type=location_type,
                salary_text=salary.matched_text if salary else raw.salary_text,
                salary_min_cad=salary.annual_min_cad if salary else None,
                salary_max_cad=salary.annual_max_cad if salary else None,
                salary_period=salary.source_period if salary else None,
                posted_at_text=raw.posted_at_text,
                seniority_hint=_derive_seniority(title, raw.jd_text),
                jd_text=_clean_text(raw.jd_text),
                is_reposted=is_reposted,
                apply_click_count=apply_click_count,
                apply_click_count_is_lower_bound=count_is_lower_bound,
                region_match_score=region_score,
                region_match_method=region_method,
                salary_source=salary_source,
            )
        )

    return normalized
