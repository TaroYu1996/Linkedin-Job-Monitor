"""Profile schema and validation for linkedin-job-monitor."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

LOCATION_TYPES = {"remote", "hybrid", "onsite", "unknown"}
SOURCE_MODES = {"linkedin", "career_pages"}
OUTPUT_MODES = {"matches_only", "include_partial_matches"}
UNKNOWN_REGION_POLICIES = {"reject", "include"}
SENIORITY_LEVELS = {
    "intern",
    "entry",
    "associate",
    "mid",
    "senior",
    "staff",
    "lead",
    "manager",
    "director",
    "vp",
    "executive",
}


@dataclass(frozen=True)
class ProfileValidationError(Exception):
    """Raised when profile validation fails."""

    message: str

    def __str__(self) -> str:
        return self.message


DEFAULT_PROFILE: dict[str, Any] = {
    "source_mode": "linkedin",
    "search_url": "",
    "career_pages": [],
    "target_roles": [],
    "regions": [],
    "region_aliases": {},
    "region_fuzzy_threshold": 0.86,
    "unknown_region_policy": "reject",
    "allowed_location_types": ["remote", "hybrid", "onsite", "unknown"],
    "minimum_salary_cad": None,
    "salary_required": False,
    "salary_hours_per_week": 40,
    "salary_weeks_per_year": 52,
    "check_detailed_jd": True,
    "prefilter_before_jd": True,
    "jd_refresh_days": 7,
    "output_mode": "matches_only",
    "seniority": [],
    "title_include_keywords": [],
    "title_exclude_keywords": [],
    "jd_include_keywords": [],
    "jd_must_have_keywords": [],
    "jd_exclude_keywords": [],
    "company_blacklist": [],
    "company_whitelist": [],
    "max_results_per_digest": 10,
    "dedupe_window_days": 14,
    "expire_after_missing_runs": 3,
    "run_history_limit": 30,
    "feedback_learning_enabled": True,
    "feedback_score_weight": 1.0,
    "runs_per_day": 2,
}

EXAMPLE_PROFILE_CANADA_ANALYTICS: dict[str, Any] = {
    "source_mode": "linkedin",
    "search_url": "https://www.linkedin.com/jobs/search/?keywords=data%20analyst&location=Canada",
    "target_roles": ["data analyst", "business analyst"],
    "regions": ["canada", "ontario", "british columbia"],
    "region_aliases": {},
    "region_fuzzy_threshold": 0.86,
    "unknown_region_policy": "reject",
    "allowed_location_types": ["remote", "hybrid", "onsite"],
    "minimum_salary_cad": 85000,
    "salary_required": False,
    "salary_hours_per_week": 40,
    "salary_weeks_per_year": 52,
    "check_detailed_jd": True,
    "prefilter_before_jd": True,
    "jd_refresh_days": 7,
    "output_mode": "include_partial_matches",
    "seniority": ["entry", "associate", "mid", "senior"],
    "title_include_keywords": [
        "analytics",
        "sql",
        "tableau",
        "stakeholder reporting",
    ],
    "title_exclude_keywords": ["intern", "volunteer", "commission"],
    "jd_include_keywords": [
        "analytics",
        "dashboard",
        "sql",
        "experimentation",
    ],
    "jd_must_have_keywords": [],
    "jd_exclude_keywords": ["commission only"],
    "company_blacklist": [],
    "company_whitelist": [],
    "max_results_per_digest": 10,
    "dedupe_window_days": 14,
    "expire_after_missing_runs": 3,
    "run_history_limit": 30,
    "feedback_learning_enabled": True,
    "feedback_score_weight": 1.0,
    "runs_per_day": 2,
}

EXAMPLE_PROFILE_CAREER_PAGES: dict[str, Any] = {
    "source_mode": "career_pages",
    "career_pages": [
        {
            "company": "TD",
            "url": "https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers",
        },
        {
            "company": "CIBC",
            "url": "https://cibc.wd3.myworkdayjobs.com/search",
        },
    ],
    "target_roles": ["marketing manager", "digital marketing"],
    "regions": ["greater toronto area"],
}


def _to_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProfileValidationError(f"{field_name} must be a list of strings")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ProfileValidationError(f"{field_name} must be a list of strings")
        token = " ".join(item.strip().lower().split())
        if token:
            cleaned.append(token)
    return cleaned


def _to_region_aliases(value: Any) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ProfileValidationError("region_aliases must map region names to string lists")
    aliases: dict[str, list[str]] = {}
    for region, raw_aliases in value.items():
        if not isinstance(region, str):
            raise ProfileValidationError("region_aliases keys must be strings")
        normalized_region = " ".join(region.strip().lower().split())
        if not normalized_region:
            continue
        aliases[normalized_region] = _to_string_list(raw_aliases, f"region_aliases.{region}")
    return aliases


def _to_career_pages(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProfileValidationError("career_pages must be a list of URLs or mappings")
    pages: list[dict[str, str]] = []
    for index, raw in enumerate(value):
        if isinstance(raw, str):
            page = {"url": raw.strip(), "company": ""}
        elif isinstance(raw, Mapping):
            page = {
                "url": str(raw.get("url") or "").strip(),
                "company": str(raw.get("company") or "").strip(),
            }
        else:
            raise ProfileValidationError(
                f"career_pages[{index}] must be a URL string or mapping"
            )
        parsed = urlsplit(page["url"])
        if parsed.scheme != "https" or not parsed.netloc:
            raise ProfileValidationError(
                f"career_pages[{index}].url must be an absolute HTTPS URL"
            )
        pages.append(page)
    return pages


def normalize_location_type(raw: str) -> str:
    value = raw.strip().lower()
    if value in {"remote", "remotely", "work from home", "wfh"}:
        return "remote"
    if value in {"hybrid", "mixed"}:
        return "hybrid"
    if value in {"on-site", "on site", "onsite", "in office", "in-office"}:
        return "onsite"
    if value in LOCATION_TYPES:
        return value
    return "unknown"


def normalize_seniority(raw: str) -> str:
    value = raw.strip().lower()
    mapping = {
        "junior": "entry",
        "jr": "entry",
        "mid-level": "mid",
        "sr": "senior",
        "principal": "staff",
        "c-level": "executive",
    }
    value = mapping.get(value, value)
    return value


def apply_defaults(profile: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(DEFAULT_PROFILE)
    merged.update(dict(profile))
    return merged


def validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    data = apply_defaults(profile)

    source_mode = data.get("source_mode")
    if source_mode not in SOURCE_MODES:
        raise ProfileValidationError("source_mode must be 'linkedin' or 'career_pages'")
    data["career_pages"] = _to_career_pages(data.get("career_pages"))

    if source_mode == "linkedin":
        if (
            not isinstance(data["search_url"], str)
            or "linkedin.com/jobs/search" not in data["search_url"]
        ):
            raise ProfileValidationError("search_url must be a LinkedIn jobs search URL")
    elif not data["career_pages"]:
        raise ProfileValidationError(
            "career_pages must contain at least one URL in career_pages mode"
        )

    if source_mode == "career_pages" and "check_detailed_jd" not in profile:
        detail_dependent_fields = (
            data.get("minimum_salary_cad") is not None
            or bool(data.get("salary_required"))
            or any(
                data.get(field)
                for field in (
                    "jd_include_keywords",
                    "jd_must_have_keywords",
                    "jd_exclude_keywords",
                )
            )
        )
        data["check_detailed_jd"] = detail_dependent_fields

    list_fields = [
        "target_roles",
        "regions",
        "allowed_location_types",
        "seniority",
        "title_include_keywords",
        "title_exclude_keywords",
        "jd_include_keywords",
        "jd_must_have_keywords",
        "jd_exclude_keywords",
        "company_blacklist",
        "company_whitelist",
    ]
    for field_name in list_fields:
        data[field_name] = _to_string_list(data.get(field_name), field_name)

    for required in ("target_roles", "regions", "allowed_location_types"):
        if not data[required]:
            raise ProfileValidationError(f"{required} must contain at least one value")

    data["region_aliases"] = _to_region_aliases(data.get("region_aliases"))
    threshold = data.get("region_fuzzy_threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not 0.5 <= threshold <= 1:
        raise ProfileValidationError("region_fuzzy_threshold must be a number between 0.5 and 1")
    data["region_fuzzy_threshold"] = float(threshold)
    if data.get("unknown_region_policy") not in UNKNOWN_REGION_POLICIES:
        raise ProfileValidationError(
            "unknown_region_policy must be 'reject' or 'include'"
        )

    data["allowed_location_types"] = [normalize_location_type(x) for x in data["allowed_location_types"]]
    if not data["allowed_location_types"]:
        data["allowed_location_types"] = ["remote", "hybrid", "onsite", "unknown"]
    for mode in data["allowed_location_types"]:
        if mode not in LOCATION_TYPES:
            raise ProfileValidationError(f"Unsupported allowed_location_types value: {mode}")

    data["seniority"] = [normalize_seniority(x) for x in data["seniority"]]
    unsupported_seniority = set(data["seniority"]) - SENIORITY_LEVELS
    if unsupported_seniority:
        values = ", ".join(sorted(unsupported_seniority))
        raise ProfileValidationError(f"Unsupported seniority value(s): {values}")

    min_salary = data.get("minimum_salary_cad")
    if min_salary is not None:
        if not isinstance(min_salary, int) or min_salary < 0:
            raise ProfileValidationError("minimum_salary_cad must be a non-negative integer or null")

    for field_name in [
        "salary_required",
        "check_detailed_jd",
        "prefilter_before_jd",
        "feedback_learning_enabled",
    ]:
        if not isinstance(data.get(field_name), bool):
            raise ProfileValidationError(f"{field_name} must be a boolean")

    feedback_weight = data.get("feedback_score_weight")
    if (
        not isinstance(feedback_weight, (int, float))
        or isinstance(feedback_weight, bool)
        or feedback_weight < 0
        or feedback_weight > 5
    ):
        raise ProfileValidationError("feedback_score_weight must be a number between 0 and 5")
    data["feedback_score_weight"] = float(feedback_weight)

    if data.get("output_mode") not in OUTPUT_MODES:
        raise ProfileValidationError(
            "output_mode must be 'matches_only' or 'include_partial_matches'"
        )

    for numeric_field in [
        "max_results_per_digest",
        "dedupe_window_days",
        "expire_after_missing_runs",
        "run_history_limit",
        "salary_hours_per_week",
        "salary_weeks_per_year",
        "runs_per_day",
    ]:
        value = data.get(numeric_field)
        if not isinstance(value, int) or value <= 0:
            raise ProfileValidationError(f"{numeric_field} must be a positive integer")

    jd_refresh_days = data.get("jd_refresh_days")
    if not isinstance(jd_refresh_days, int) or isinstance(jd_refresh_days, bool) or jd_refresh_days < 0:
        raise ProfileValidationError("jd_refresh_days must be a non-negative integer")

    return data
