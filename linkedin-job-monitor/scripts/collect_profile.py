"""Helpers for building and updating a validated monitor profile."""

from __future__ import annotations

from typing import Any, Mapping

from config_schema import apply_defaults, validate_profile


def parse_profile_input(conversation_fields: Mapping[str, Any]) -> dict[str, Any]:
    """Convert conversationally gathered fields into a normalized profile."""
    return validate_profile(conversation_fields)


def merge_profile_update(existing_profile: Mapping[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    """Apply partial field updates while preserving untouched fields."""
    merged = apply_defaults(existing_profile)
    for key, value in updates.items():
        merged[key] = value
    if updates.get("source_mode") != existing_profile.get("source_mode"):
        if "check_detailed_jd" not in updates:
            if updates.get("source_mode") == "career_pages":
                merged["check_detailed_jd"] = (
                    merged.get("minimum_salary_cad") is not None
                    or bool(merged.get("salary_required"))
                    or any(
                        merged.get(field)
                        for field in (
                            "jd_include_keywords",
                            "jd_must_have_keywords",
                            "jd_exclude_keywords",
                        )
                    )
                )
            else:
                merged["check_detailed_jd"] = True
    elif (
        merged.get("source_mode") == "career_pages"
        and "check_detailed_jd" not in updates
        and any(
            updates.get(field)
            for field in (
                "jd_include_keywords",
                "jd_must_have_keywords",
                "jd_exclude_keywords",
            )
        )
    ):
        # Do not leave newly added JD rules inert on an existing lightweight task.
        merged["check_detailed_jd"] = True
    return validate_profile(merged)


def profile_exists(profile: Mapping[str, Any] | None) -> bool:
    """Check if a profile is available and appears minimally complete."""
    if not profile:
        return False
    candidate = apply_defaults(profile)
    source_ready = (
        bool(candidate.get("career_pages"))
        if candidate.get("source_mode") == "career_pages"
        else bool(candidate.get("search_url"))
    )
    return bool(source_ready and candidate.get("target_roles") and candidate.get("regions"))


def required_setup_fields(source_mode: str | None = None) -> list[str]:
    """Return the minimum first-time fields for the selected source."""
    if source_mode is None:
        return ["source_mode"]
    if source_mode == "career_pages":
        return ["career_pages", "target_roles", "regions"]
    if source_mode == "linkedin":
        return ["search_url", "target_roles", "regions", "allowed_location_types"]
    raise ValueError("source_mode must be 'linkedin' or 'career_pages'")
