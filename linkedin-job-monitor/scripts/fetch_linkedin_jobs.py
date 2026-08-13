"""Fetch raw LinkedIn jobs from an authenticated session.

This module intentionally focuses on collection only. Filtering/ranking belong to later stages.
"""

from __future__ import annotations

from dataclasses import dataclass
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


class LinkedInSessionAdapter(Protocol):
    """Runtime adapter for authenticated browser/session control."""

    def goto(self, url: str) -> None: ...

    def collect_job_cards(self) -> list[Any]: ...

    def open_job_card(self, card: Any) -> None: ...

    def extract_visible_text(self, selector: str) -> str | None: ...

    def extract_attr(self, selector: str, attr: str) -> str | None: ...

    # Optional: return metadata visible on the result card before it is opened.
    # Supported keys are posted_at_text, is_reposted, and apply_click_count_text.
    def extract_job_card_metadata(self, card: Any) -> Mapping[str, Any]: ...


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
    session.goto(search_url)
    cards = session.collect_job_cards()
    jobs: list[RawLinkedInJob] = []

    for card in cards[:max_cards]:
        card_metadata: Mapping[str, Any] = {}
        extract_card_metadata = getattr(session, "extract_job_card_metadata", None)
        if callable(extract_card_metadata):
            card_metadata = extract_card_metadata(card) or {}
        session.open_job_card(card)
        title = session.extract_visible_text(".job-details-jobs-unified-top-card__job-title") or ""
        company = session.extract_visible_text(".job-details-jobs-unified-top-card__company-name") or ""
        location_text = session.extract_visible_text(".job-details-jobs-unified-top-card__bullet") or ""
        work_mode_text = session.extract_visible_text(".jobs-unified-top-card__workplace-type")
        salary_text = session.extract_visible_text(".job-details-jobs-unified-top-card__job-insight")
        detail_metadata_text = session.extract_visible_text(
            ".job-details-jobs-unified-top-card__primary-description"
        )
        posted_at_text = card_metadata.get("posted_at_text") or detail_metadata_text
        job_url = session.extract_attr("a.job-details-jobs-unified-top-card__job-title-link", "href") or ""
        job_id = session.extract_attr(".jobs-unified-top-card", "data-job-id")
        jd_text = ""
        if check_detailed_jd:
            jd_text = session.extract_visible_text(".jobs-description-content__text") or ""

        if not (title and company and job_url):
            continue

        jobs.append(
            RawLinkedInJob(
                title=title.strip(),
                company=company.strip(),
                location_text=location_text.strip(),
                work_mode_text=(work_mode_text or "").strip() or None,
                salary_text=(salary_text or "").strip() or None,
                posted_at_text=(posted_at_text or "").strip() or None,
                job_url=job_url.strip(),
                job_id=(job_id or "").strip() or None,
                jd_text=jd_text.strip(),
                is_reposted=card_metadata.get("is_reposted"),
                apply_click_count_text=(
                    str(card_metadata["apply_click_count_text"]).strip()
                    if card_metadata.get("apply_click_count_text") is not None
                    else None
                ),
            )
        )

    return jobs
