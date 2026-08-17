"""Deterministic hard filtering for normalized jobs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from normalize_jobs import NormalizedJob


def _matches_target_role(title: str, target_roles: Iterable[str]) -> bool:
    title_lower = title.lower()
    title_tokens = set(re.findall(r"[a-z0-9]+", title_lower))
    for role in target_roles:
        role_lower = role.lower()
        role_tokens = set(re.findall(r"[a-z0-9]+", role_lower))
        if role_lower in title_lower or (role_tokens and role_tokens <= title_tokens):
            return True
    return False


@dataclass
class FilterResult:
    passed: list[NormalizedJob]
    rejected: list[tuple[NormalizedJob, list[str]]]


def apply_card_prefilters(jobs: list[NormalizedJob], profile: dict) -> FilterResult:
    """Apply only definitive card-level filters before any JD is opened.

    Salary, JD keyword, and JD-derived seniority decisions remain in the full
    filter because an empty card field is not evidence that the JD lacks it.
    """
    passed: list[NormalizedJob] = []
    rejected: list[tuple[NormalizedJob, list[str]]] = []
    allowed_regions = set(profile.get("regions", []))
    allowed_location_types = set(profile.get("allowed_location_types", []))
    title_includes = profile.get("title_include_keywords", [])
    title_excludes = profile.get("title_exclude_keywords", [])
    whitelist = set(profile.get("company_whitelist", []))
    blacklist = set(profile.get("company_blacklist", []))
    unknown_region_policy = profile.get("unknown_region_policy", "reject")
    target_roles = profile.get("target_roles", [])

    for job in jobs:
        reasons: list[str] = []
        title = job.title.lower()
        company = job.company.lower()
        if (
            profile.get("source_mode") == "career_pages"
            and target_roles
            and not _matches_target_role(title, target_roles)
        ):
            reasons.append("target_role_mismatch")
        if allowed_regions:
            if job.normalized_region == "unknown":
                if unknown_region_policy != "include":
                    reasons.append("region_unknown")
            elif job.normalized_region not in allowed_regions:
                reasons.append("region_mismatch")
        if allowed_location_types and job.location_type not in allowed_location_types:
            reasons.append("location_type_mismatch")
        if title_includes and not _contains_any(title, title_includes):
            reasons.append("title_missing_include_keywords")
        if title_excludes and _contains_any(title, title_excludes):
            reasons.append("title_contains_excluded_keyword")
        if whitelist and company not in whitelist:
            reasons.append("company_not_whitelisted")
        if blacklist and company in blacklist:
            reasons.append("company_blacklisted")
        if reasons:
            rejected.append((job, reasons))
        else:
            passed.append(job)
    return FilterResult(passed=passed, rejected=rejected)


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in needles)


def _contains_all(text: str, needles: Iterable[str]) -> bool:
    lowered = text.lower()
    return all(token in lowered for token in needles)


def apply_hard_filters(jobs: list[NormalizedJob], profile: dict) -> FilterResult:
    passed: list[NormalizedJob] = []
    rejected: list[tuple[NormalizedJob, list[str]]] = []
    allowed_regions = set(profile.get("regions", []))
    allowed_location_types = set(profile.get("allowed_location_types", []))
    seniority_filters = set(profile.get("seniority", []))
    title_includes = profile.get("title_include_keywords", [])
    title_excludes = profile.get("title_exclude_keywords", [])
    jd_includes = profile.get("jd_include_keywords", [])
    jd_must_have = profile.get("jd_must_have_keywords", [])
    jd_excludes = profile.get("jd_exclude_keywords", [])
    whitelist = set(profile.get("company_whitelist", []))
    blacklist = set(profile.get("company_blacklist", []))
    unknown_region_policy = profile.get("unknown_region_policy", "reject")
    target_roles = profile.get("target_roles", [])

    for job in jobs:
        reasons: list[str] = []
        title = job.title.lower()
        jd = job.jd_text.lower()
        company = job.company.lower()

        if (
            profile.get("source_mode") == "career_pages"
            and target_roles
            and not _matches_target_role(title, target_roles)
        ):
            reasons.append("target_role_mismatch")

        if allowed_regions:
            if job.normalized_region == "unknown":
                if unknown_region_policy != "include":
                    reasons.append("region_unknown")
            elif job.normalized_region not in allowed_regions:
                reasons.append("region_mismatch")

        if allowed_location_types and job.location_type not in allowed_location_types:
            reasons.append("location_type_mismatch")

        minimum_salary = profile.get("minimum_salary_cad")
        if profile.get("salary_required") and job.salary_min_cad is None:
            reasons.append("salary_required_missing")
        if minimum_salary is not None and job.salary_min_cad is not None and job.salary_min_cad < minimum_salary:
            reasons.append("salary_below_minimum")

        if seniority_filters and job.seniority_hint and job.seniority_hint not in seniority_filters:
            reasons.append("seniority_mismatch")

        if title_includes and not _contains_any(title, title_includes):
            reasons.append("title_missing_include_keywords")

        if title_excludes and _contains_any(title, title_excludes):
            reasons.append("title_contains_excluded_keyword")

        if profile.get("check_detailed_jd", True):
            if jd_includes and not _contains_any(jd, jd_includes):
                reasons.append("jd_missing_include_keywords")

            if jd_must_have and not _contains_all(jd, jd_must_have):
                reasons.append("jd_missing_must_have_keywords")

            if jd_excludes and _contains_any(jd, jd_excludes):
                reasons.append("jd_contains_excluded_keyword")

        if whitelist and company not in whitelist:
            reasons.append("company_not_whitelisted")

        if blacklist and company in blacklist:
            reasons.append("company_blacklisted")

        if reasons:
            rejected.append((job, reasons))
        else:
            passed.append(job)

    return FilterResult(passed=passed, rejected=rejected)
