"""Profile-driven scoring for filtered jobs."""

from __future__ import annotations

from dataclasses import dataclass

from normalize_jobs import NormalizedJob


@dataclass
class ScoredJob:
    job: NormalizedJob
    score: float
    reasons: list[str]
    dedupe_status: str
    match_status: str = "match"
    mismatch_reasons: list[str] | None = None


def _count_hits(text: str, keywords: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for kw in keywords if kw in lowered)


def score_jobs(jobs_with_status: list[tuple[NormalizedJob, str]], profile: dict) -> list[ScoredJob]:
    scored: list[ScoredJob] = []

    for job, dedupe_status in jobs_with_status:
        title = job.title.lower()
        jd = job.jd_text.lower()
        score = 0.0
        reasons: list[str] = []

        role_hits = _count_hits(f"{title} {jd}", profile.get("target_roles", []))
        if role_hits:
            score += role_hits * 3.0
            reasons.append(f"role_hits:{role_hits}")

        title_hits = _count_hits(title, profile.get("title_include_keywords", []))
        if title_hits:
            score += title_hits * 2.0
            reasons.append(f"title_hits:{title_hits}")

        if profile.get("check_detailed_jd", True):
            jd_hits = _count_hits(jd, profile.get("jd_include_keywords", []))
            if jd_hits:
                score += jd_hits * 1.5
                reasons.append(f"jd_hits:{jd_hits}")

        if job.location_type in set(profile.get("allowed_location_types", [])):
            score += 1.0
            reasons.append("location_type_fit")

        min_salary = profile.get("minimum_salary_cad")
        if min_salary is not None and job.salary_min_cad is not None:
            salary_delta = max(job.salary_min_cad - min_salary, 0)
            bonus = min(salary_delta / 10000, 3.0)
            if bonus > 0:
                score += bonus
                reasons.append("salary_above_min")

        if dedupe_status == "updated":
            score += 0.25
            reasons.append("job_updated")

        scored.append(ScoredJob(job=job, score=round(score, 3), reasons=reasons, dedupe_status=dedupe_status))

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored
