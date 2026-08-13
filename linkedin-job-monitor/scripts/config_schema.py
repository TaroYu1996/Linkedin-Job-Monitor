"""Profile schema and validation for linkedin-job-monitor."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

LOCATION_TYPES = {"remote", "hybrid", "onsite", "unknown"}
OUTPUT_MODES = {"matches_only", "include_partial_matches"}
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


REQUIRED_FIELDS = {
    "search_url",
    "target_roles",
    "regions",
    "allowed_location_types",
}

DEFAULT_PROFILE: dict[str, Any] = {
    "search_url": "",
    "target_roles": [],
    "regions": [],
    "allowed_location_types": ["remote", "hybrid", "onsite", "unknown"],
    "minimum_salary_cad": None,
    "salary_required": False,
    "check_detailed_jd": True,
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
    "runs_per_day": 2,
}

EXAMPLE_PROFILE_CANADA_ANALYTICS: dict[str, Any] = {
    "search_url": "https://www.linkedin.com/jobs/search/?keywords=data%20analyst&location=Canada",
    "target_roles": ["data analyst", "business analyst"],
    "regions": ["canada", "ontario", "british columbia"],
    "allowed_location_types": ["remote", "hybrid", "onsite"],
    "minimum_salary_cad": 85000,
    "salary_required": False,
    "check_detailed_jd": True,
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
    "runs_per_day": 2,
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


def normalize_location_type(raw: str) -> str:
    value = raw.strip().lower()
    if value in {"remote", "remotely", "work from home", "wfh"}:
        return "remote"
    if value in {"hybrid", "mixed"}:
        return "hybrid"
    if value in {"on-site", "onsite", "in office", "in-office"}:
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
    return value if value in SENIORITY_LEVELS else "mid"


def apply_defaults(profile: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(DEFAULT_PROFILE)
    merged.update(dict(profile))
    return merged


def validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    data = apply_defaults(profile)

    for required in REQUIRED_FIELDS:
        if required not in data:
            raise ProfileValidationError(f"Missing required field: {required}")

    if not isinstance(data["search_url"], str) or "linkedin.com/jobs/search" not in data["search_url"]:
        raise ProfileValidationError("search_url must be a LinkedIn jobs search URL")

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

    data["allowed_location_types"] = [normalize_location_type(x) for x in data["allowed_location_types"]]
    if not data["allowed_location_types"]:
        data["allowed_location_types"] = ["remote", "hybrid", "onsite", "unknown"]
    for mode in data["allowed_location_types"]:
        if mode not in LOCATION_TYPES:
            raise ProfileValidationError(f"Unsupported allowed_location_types value: {mode}")

    data["seniority"] = [normalize_seniority(x) for x in data["seniority"]]

    min_salary = data.get("minimum_salary_cad")
    if min_salary is not None:
        if not isinstance(min_salary, int) or min_salary < 0:
            raise ProfileValidationError("minimum_salary_cad must be a non-negative integer or null")

    for field_name in ["salary_required", "check_detailed_jd"]:
        if not isinstance(data.get(field_name), bool):
            raise ProfileValidationError(f"{field_name} must be a boolean")

    if data.get("output_mode") not in OUTPUT_MODES:
        raise ProfileValidationError(
            "output_mode must be 'matches_only' or 'include_partial_matches'"
        )

    for numeric_field in ["max_results_per_digest", "dedupe_window_days", "runs_per_day"]:
        value = data.get(numeric_field)
        if not isinstance(value, int) or value <= 0:
            raise ProfileValidationError(f"{numeric_field} must be a positive integer")

    return data
