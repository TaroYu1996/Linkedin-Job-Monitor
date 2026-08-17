"""Fetch raw LinkedIn jobs from an authenticated session.

This module intentionally focuses on collection only. Filtering/ranking belong to later stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Mapping, Protocol


@dataclass
class RawLinkedInJob:
    title: str
    company: str
    location_text: str
    work_mode_text: str | None
    salary_text: str | None
    posted_at_text: str | None
    job_url: str
    job_id: str | None
    jd_text: str
    is_reposted: bool | None = None
    apply_click_count_text: str | None = None
    source_namespace: str | None = None
    source_mode: str = "linkedin"


@dataclass
class FetchStats:
    cards_collected: int = 0
    cards_attempted: int = 0
    jobs_parsed: int = 0
    parse_failed: int = 0
    fetch_errors: int = 0
    truncated: bool = False
    collection_complete: bool = False
    fatal_error: str | None = None
    collection_mode: str = "legacy_details"
    summary_host_calls: int = 0
    detail_fetch_attempted: int = 0
    detail_fetch_succeeded: int = 0
    detail_fetch_skipped: int = 0
    detail_fetch_failed: int = 0
    duplicate_cards_skipped: int = 0
    summary_duration_ms: float = 0.0
    detail_duration_ms: float = 0.0
    pages_configured: int = 0
    pages_succeeded: int = 0
    pages_failed: int = 0
    page_errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cards_collected": self.cards_collected,
            "cards_attempted": self.cards_attempted,
            "jobs_parsed": self.jobs_parsed,
            "parse_failed": self.parse_failed,
            "fetch_errors": self.fetch_errors,
            "truncated": self.truncated,
            "collection_complete": self.collection_complete,
            "fatal_error": self.fatal_error,
            "collection_mode": self.collection_mode,
            "summary_host_calls": self.summary_host_calls,
            "detail_fetch_attempted": self.detail_fetch_attempted,
            "detail_fetch_succeeded": self.detail_fetch_succeeded,
            "detail_fetch_skipped": self.detail_fetch_skipped,
            "detail_fetch_failed": self.detail_fetch_failed,
            "duplicate_cards_skipped": self.duplicate_cards_skipped,
            "summary_duration_ms": self.summary_duration_ms,
            "detail_duration_ms": self.detail_duration_ms,
            "pages_configured": self.pages_configured,
            "pages_succeeded": self.pages_succeeded,
            "pages_failed": self.pages_failed,
            "page_errors": self.page_errors,
        }


@dataclass
class FetchResult:
    jobs: list[RawLinkedInJob]
    stats: FetchStats


@dataclass
class JobCandidate:
    """A card-level job summary plus the adapter reference needed to open its JD."""

    raw: RawLinkedInJob
    detail_reference: Any
    details_loaded: bool = False


@dataclass
class CandidateFetchResult:
    candidates: list[JobCandidate]
    stats: FetchStats


class LinkedInSessionAdapter(Protocol):
    """Runtime adapter for authenticated browser/session control."""

    def goto(self, url: str) -> None: ...

    def collect_job_cards(self) -> list[Any]: ...

    # Preferred two-stage path. Return every visible result-card field in one
    # host call without opening job details. A mapping may include `card_ref`
    # for the later extract_job_details call; otherwise the mapping is reused.
    def collect_job_summaries(self, max_cards: int) -> list[Mapping[str, Any]]: ...

    def open_job_card(self, card: Any) -> None: ...

    def extract_visible_text(self, selector: str) -> str | None: ...

    def extract_attr(self, selector: str, attr: str) -> str | None: ...

    # Optional: return metadata visible on the result card before it is opened.
    # Supported keys are posted_at_text, is_reposted, and apply_click_count_text.
    def extract_job_card_metadata(self, card: Any) -> Mapping[str, Any]: ...

    # Optional fast path: select/open one card and return all supported job fields
    # in one host call instead of many selector round trips.
    def extract_job_details(
        self, card: Any, check_detailed_jd: bool
    ) -> Mapping[str, Any]: ...


def _raw_from_mapping(data: Mapping[str, Any], check_detailed_jd: bool = False) -> RawLinkedInJob:
    return RawLinkedInJob(
        title=str(data.get("title") or "").strip(),
        company=str(data.get("company") or "").strip(),
        location_text=str(data.get("location_text") or "").strip(),
        work_mode_text=str(data.get("work_mode_text") or "").strip() or None,
        salary_text=str(data.get("salary_text") or "").strip() or None,
        posted_at_text=str(data.get("posted_at_text") or "").strip() or None,
        job_url=str(data.get("job_url") or "").strip(),
        job_id=str(data.get("job_id") or "").strip() or None,
        jd_text=(str(data.get("jd_text") or "").strip() if check_detailed_jd else ""),
        is_reposted=data.get("is_reposted"),
        apply_click_count_text=(
            str(data.get("apply_click_count_text")).strip()
            if data.get("apply_click_count_text") is not None
            else None
        ),
        source_namespace=str(data.get("source_namespace") or "").strip() or None,
        source_mode=str(data.get("source_mode") or "linkedin").strip(),
    )


def _merge_details(
    summary: RawLinkedInJob,
    details: Mapping[str, Any],
    check_detailed_jd: bool,
) -> RawLinkedInJob:
    merged = {
        "title": details.get("title") or summary.title,
        "company": details.get("company") or summary.company,
        "location_text": details.get("location_text") or summary.location_text,
        "work_mode_text": details.get("work_mode_text") or summary.work_mode_text,
        "salary_text": details.get("salary_text") or summary.salary_text,
        "posted_at_text": details.get("posted_at_text") or summary.posted_at_text,
        "job_url": details.get("job_url") or summary.job_url,
        "job_id": details.get("job_id") or summary.job_id,
        "jd_text": details.get("jd_text") or summary.jd_text,
        "is_reposted": (
            details.get("is_reposted")
            if details.get("is_reposted") is not None
            else summary.is_reposted
        ),
        "apply_click_count_text": (
            details.get("apply_click_count_text") or summary.apply_click_count_text
        ),
        "source_namespace": details.get("source_namespace") or summary.source_namespace,
        "source_mode": details.get("source_mode") or summary.source_mode,
    }
    return _raw_from_mapping(merged, check_detailed_jd=check_detailed_jd)


def collect_linkedin_job_candidates_report(
    search_url: str,
    session: LinkedInSessionAdapter,
    max_cards: int = 100,
    check_detailed_jd: bool = True,
) -> CandidateFetchResult:
    """Collect cheap card summaries first, falling back to the legacy full-detail path."""
    collect_summaries = getattr(session, "collect_job_summaries", None)
    if not callable(collect_summaries):
        legacy = fetch_linkedin_jobs_report(
            search_url,
            session=session,
            max_cards=max_cards,
            check_detailed_jd=check_detailed_jd,
        )
        return CandidateFetchResult(
            candidates=[JobCandidate(raw=job, detail_reference=None, details_loaded=True) for job in legacy.jobs],
            stats=legacy.stats,
        )

    stats = FetchStats(collection_mode="batch_summaries")
    started = perf_counter()
    try:
        session.goto(search_url)
        summaries = collect_summaries(max_cards)
        stats.summary_host_calls = 1
    except Exception as exc:
        stats.fetch_errors = 1
        stats.fatal_error = f"{type(exc).__name__}: {exc}"
        stats.summary_duration_ms = round((perf_counter() - started) * 1000, 3)
        return CandidateFetchResult(candidates=[], stats=stats)

    stats.summary_duration_ms = round((perf_counter() - started) * 1000, 3)
    stats.cards_collected = len(summaries)
    stats.truncated = len(summaries) > max_cards
    candidates: list[JobCandidate] = []
    for summary in summaries[:max_cards]:
        stats.cards_attempted += 1
        try:
            raw = _raw_from_mapping(summary, check_detailed_jd=False)
        except Exception:
            stats.parse_failed += 1
            continue
        if not (raw.title and raw.company and raw.job_url):
            stats.parse_failed += 1
            continue
        candidates.append(
            JobCandidate(
                raw=raw,
                detail_reference=summary.get("card_ref", summary),
                details_loaded=False,
            )
        )
        stats.jobs_parsed += 1

    stats.collection_complete = (
        not stats.truncated and stats.fetch_errors == 0 and stats.parse_failed == 0
    )
    return CandidateFetchResult(candidates=candidates, stats=stats)


def hydrate_job_candidates(
    candidates: list[JobCandidate],
    detail_indexes: set[int],
    session: LinkedInSessionAdapter,
    check_detailed_jd: bool,
    stats: FetchStats,
) -> list[JobCandidate]:
    """Fetch details only for selected candidates and retain summaries for skipped jobs."""
    if stats.collection_mode == "legacy_details":
        return candidates

    extract_details = getattr(session, "extract_job_details", None)
    stats.detail_fetch_skipped += len(candidates) - len(detail_indexes)
    if not detail_indexes:
        return candidates
    if not callable(extract_details):
        stats.fetch_errors += len(detail_indexes)
        stats.detail_fetch_failed += len(detail_indexes)
        stats.collection_complete = False
        return [item for index, item in enumerate(candidates) if index not in detail_indexes]

    started = perf_counter()
    hydrated: list[JobCandidate] = []
    for index, candidate in enumerate(candidates):
        if index not in detail_indexes:
            hydrated.append(candidate)
            continue
        stats.detail_fetch_attempted += 1
        try:
            details = extract_details(candidate.detail_reference, check_detailed_jd) or {}
            raw = _merge_details(candidate.raw, details, check_detailed_jd)
            if not (raw.title and raw.company and raw.job_url):
                raise ValueError("detail response is missing title, company, or job_url")
        except Exception:
            stats.fetch_errors += 1
            stats.detail_fetch_failed += 1
            stats.collection_complete = False
            continue
        hydrated.append(
            JobCandidate(raw=raw, detail_reference=candidate.detail_reference, details_loaded=True)
        )
        stats.detail_fetch_succeeded += 1
    stats.detail_duration_ms = round((perf_counter() - started) * 1000, 3)
    return hydrated


def fetch_linkedin_jobs(
    search_url: str,
    session: LinkedInSessionAdapter,
    max_cards: int = 100,
    check_detailed_jd: bool = True,
) -> list[RawLinkedInJob]:
    """Fetch job cards and corresponding job details from LinkedIn search results.

    TODO: supply a concrete `LinkedInSessionAdapter` for the host runtime (Playwright,
    Selenium, hosted browser, etc.).
    """
    return fetch_linkedin_jobs_report(
        search_url,
        session=session,
        max_cards=max_cards,
        check_detailed_jd=check_detailed_jd,
    ).jobs


def fetch_linkedin_jobs_report(
    search_url: str,
    session: LinkedInSessionAdapter,
    max_cards: int = 100,
    check_detailed_jd: bool = True,
) -> FetchResult:
    """Fetch jobs and return stage-level statistics without failing the full run per card."""
    stats = FetchStats()
    summary_started = perf_counter()
    try:
        session.goto(search_url)
        cards = session.collect_job_cards()
    except Exception as exc:
        stats.fetch_errors = 1
        stats.fatal_error = f"{type(exc).__name__}: {exc}"
        stats.summary_duration_ms = round((perf_counter() - summary_started) * 1000, 3)
        return FetchResult(jobs=[], stats=stats)

    stats.summary_duration_ms = round((perf_counter() - summary_started) * 1000, 3)
    stats.cards_collected = len(cards)
    stats.truncated = len(cards) > max_cards
    jobs: list[RawLinkedInJob] = []

    detail_started = perf_counter()
    for card in cards[:max_cards]:
        stats.cards_attempted += 1
        stats.detail_fetch_attempted += 1
        try:
            card_metadata: Mapping[str, Any] = {}
            extract_card_metadata = getattr(session, "extract_job_card_metadata", None)
            if callable(extract_card_metadata):
                card_metadata = extract_card_metadata(card) or {}
            extract_job_details = getattr(session, "extract_job_details", None)
            if callable(extract_job_details):
                details = extract_job_details(card, check_detailed_jd) or {}
                title = str(details.get("title") or "")
                company = str(details.get("company") or "")
                location_text = str(details.get("location_text") or "")
                work_mode_text = details.get("work_mode_text")
                salary_text = details.get("salary_text")
                posted_at_text = details.get("posted_at_text") or card_metadata.get(
                    "posted_at_text"
                )
                job_url = str(details.get("job_url") or "")
                job_id = details.get("job_id")
                jd_text = str(details.get("jd_text") or "") if check_detailed_jd else ""
                card_metadata = {**card_metadata, **details}
            else:
                session.open_job_card(card)
                title = session.extract_visible_text(
                    ".job-details-jobs-unified-top-card__job-title"
                ) or ""
                company = session.extract_visible_text(
                    ".job-details-jobs-unified-top-card__company-name"
                ) or ""
                location_text = session.extract_visible_text(
                    ".job-details-jobs-unified-top-card__bullet"
                ) or ""
                work_mode_text = session.extract_visible_text(
                    ".jobs-unified-top-card__workplace-type"
                )
                salary_text = session.extract_visible_text(
                    ".job-details-jobs-unified-top-card__job-insight"
                )
                detail_metadata_text = session.extract_visible_text(
                    ".job-details-jobs-unified-top-card__primary-description"
                )
                posted_at_text = card_metadata.get("posted_at_text") or detail_metadata_text
                job_url = session.extract_attr(
                    "a.job-details-jobs-unified-top-card__job-title-link", "href"
                ) or ""
                job_id = session.extract_attr(".jobs-unified-top-card", "data-job-id")
                jd_text = ""
                if check_detailed_jd:
                    jd_text = session.extract_visible_text(".jobs-description-content__text") or ""
        except Exception:
            stats.fetch_errors += 1
            stats.detail_fetch_failed += 1
            continue

        if not (title and company and job_url):
            stats.parse_failed += 1
            stats.detail_fetch_failed += 1
            continue

        jobs.append(
            RawLinkedInJob(
                title=title.strip(),
                company=company.strip(),
                location_text=location_text.strip(),
                work_mode_text=str(work_mode_text or "").strip() or None,
                salary_text=str(salary_text or "").strip() or None,
                posted_at_text=str(posted_at_text or "").strip() or None,
                job_url=job_url.strip(),
                job_id=str(job_id or "").strip() or None,
                jd_text=jd_text.strip(),
                is_reposted=card_metadata.get("is_reposted"),
                apply_click_count_text=(
                    str(card_metadata["apply_click_count_text"]).strip()
                    if card_metadata.get("apply_click_count_text") is not None
                    else None
                ),
            )
        )
        stats.jobs_parsed += 1
        stats.detail_fetch_succeeded += 1

    stats.detail_duration_ms = round((perf_counter() - detail_started) * 1000, 3)

    stats.collection_complete = (
        not stats.truncated
        and stats.fetch_errors == 0
        and stats.parse_failed == 0
    )
    return FetchResult(jobs=jobs, stats=stats)
