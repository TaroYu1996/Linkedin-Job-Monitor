"""Collect public company-career jobs from supported public ATS pages."""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from time import perf_counter
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from fetch_linkedin_jobs import (
    CandidateFetchResult,
    FetchStats,
    JobCandidate,
    _raw_from_mapping,
)


class CareerPageSessionAdapter(Protocol):
    """Optional host adapter for career platforms not handled by the built-in client."""

    def collect_career_job_summaries(
        self,
        page: Mapping[str, str],
        max_cards: int,
        target_roles: list[str],
    ) -> list[Mapping[str, Any]]: ...

    def extract_job_details(
        self, reference: Any, check_detailed_jd: bool
    ) -> Mapping[str, Any]: ...


_WORKDAY_VALUE_RE = {
    key: re.compile(rf'{key}:\s*"([^"]+)"')
    for key in ("tenant", "siteId")
}
_WORKDAY_LOCALE_RE = re.compile(r'(?:requestLocale|locale):\s*"([^"]+)"')
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_OG_DESCRIPTION_RE = re.compile(
    r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_PHENOM_APP_RE = re.compile(
    r"var\s+phApp\s*=\s*phApp\s*\|\|\s*(\{.*?\});\s*phApp\.ddo",
    re.DOTALL,
)
_PHENOM_DDO_RE = re.compile(
    r"phApp\.ddo\s*=\s*(\{.*?\});\s*phApp\.experimentData",
    re.DOTALL,
)
_SCOTIA_ROW_RE = re.compile(
    r'<tr[^>]+class=["\'][^"\']*\bdata-row\b[^"\']*["\'][^>]*>(.*?)</tr>',
    re.IGNORECASE | re.DOTALL,
)
_SCOTIA_TITLE_RE = re.compile(
    r'<a[^>]+href=["\']([^"\']+)["\'][^>]+class=["\'][^"\']*'
    r'\bjobTitle-link\b[^"\']*["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SCOTIA_DATE_RE = re.compile(
    r'<td[^>]+class=["\'][^"\']*\bcolDate\b[^"\']*["\'][^>]*>(.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)
_SCOTIA_LOCATION_RE = re.compile(
    r'<td[^>]+class=["\'][^"\']*\bcolLocation\b[^"\']*["\'][^>]*>(.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)
_SCOTIA_TOTAL_RE = re.compile(
    r'class=["\']paginationLabel["\'][^>]*>.*?\bof\s*<b>([\d,]+)</b>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WORKDAY_NON_FACET_PARAMS = {
    "createnewalert",
    "from",
    "keywords",
    "locale",
    "location",
    "locationsearch",
    "q",
    "query",
    "sort",
    "sortcolumn",
    "sortdirection",
    "startrow",
}
_MAX_SEARCH_PAGES_PER_ROLE = 10
_BANK_NAMESPACE_BY_HOST = {
    "bmo.wd3.myworkdayjobs.com": "bank/bmo",
    "jobs.bmo.com": "bank/bmo",
    "jobs.rbc.com": "bank/rbc",
    "jobs.scotiabank.com": "bank/scotiabank",
}


def career_source_namespace(url: str) -> str:
    parsed = urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
        parts = parts[1:]
    site = parts[0] if parts else "careers"
    return f"{parsed.netloc.lower()}/{site.lower()}"


def _source_namespace(url: str) -> str:
    """Use one identity scope when an employer exposes the same jobs twice."""
    host = urlsplit(url).netloc.lower()
    return _BANK_NAMESPACE_BY_HOST.get(host, career_source_namespace(url))


def _clean_html_text(value: Any) -> str:
    source = html.unescape(str(value or ""))
    source = _TAG_RE.sub(" ", source)
    return " ".join(html.unescape(source).split())


def _query_url(page_url: str, updates: Mapping[str, Any]) -> str:
    parsed = urlsplit(page_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    for key, value in updates.items():
        query[key] = [str(value)]
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), "")
    )


def _workday_applied_facets(page_url: str) -> dict[str, list[str]]:
    query = parse_qs(urlsplit(page_url).query, keep_blank_values=False)
    return {
        key: values
        for key, values in query.items()
        if key.lower() not in _WORKDAY_NON_FACET_PARAMS and values
    }


def _title_matches_target(title: Any, target: str) -> bool:
    title_lower = str(title or "").lower()
    target_lower = target.lower()
    title_tokens = set(re.findall(r"[a-z0-9]+", title_lower))
    target_tokens = set(re.findall(r"[a-z0-9]+", target_lower))
    return target_lower in title_lower or bool(target_tokens and target_tokens <= title_tokens)


def _json_ld_job_description(source: str) -> str:
    for match in _JSON_LD_RE.finditer(source):
        try:
            value = json.loads(match.group(1))
        except (TypeError, ValueError):
            continue
        postings = value if isinstance(value, list) else [value]
        for posting in postings:
            if not isinstance(posting, Mapping):
                continue
            posting_type = posting.get("@type")
            types = posting_type if isinstance(posting_type, list) else [posting_type]
            if "JobPosting" in types and posting.get("description"):
                return _clean_html_text(posting["description"])
    return ""


class _ItempropDescriptionParser(HTMLParser):
    _VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []
        self.finished = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if self.finished:
            return
        values = dict(attrs)
        if not self.depth and values.get("itemprop") == "description":
            self.depth = 1
        elif self.depth and tag not in self._VOID_TAGS:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self.depth or tag in self._VOID_TAGS:
            return
        self.depth -= 1
        if not self.depth:
            self.finished = True

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self.parts).split())


def _detail_description(source: str) -> str:
    description = _json_ld_job_description(source)
    if description:
        return description
    parser = _ItempropDescriptionParser()
    parser.feed(source)
    if parser.text():
        return parser.text()
    match = _OG_DESCRIPTION_RE.search(source)
    return _clean_html_text(match.group(1)) if match else ""


def _workday_company(page: Mapping[str, str], tenant: str) -> str:
    configured = str(page.get("company") or "").strip()
    return configured or tenant.upper()


def _job_id(posting: Mapping[str, Any]) -> str | None:
    bullet_fields = posting.get("bulletFields") or []
    if bullet_fields and str(bullet_fields[0]).strip():
        return str(bullet_fields[0]).strip()
    external_path = str(posting.get("externalPath") or "")
    suffix = external_path.rsplit("_", 1)[-1].strip()
    return suffix if suffix and suffix != external_path else None


class WorkdayCareerSession:
    """Read public Workday external-career search and JobPosting pages."""

    def __init__(
        self,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: int = 20,
    ) -> None:
        self._opener = opener
        self.timeout_seconds = timeout_seconds
        self._sites: dict[str, dict[str, str]] = {}
        self.last_collection_truncated = False
        self.last_host_calls = 0

    def _read(self, request: Request) -> bytes:
        self.last_host_calls += 1
        with self._opener(request, timeout=self.timeout_seconds) as response:
            return response.read()

    def _discover(self, page_url: str) -> dict[str, str]:
        cached = self._sites.get(page_url)
        if cached is not None:
            return cached
        request = Request(
            page_url,
            headers={"User-Agent": "LinkedIn-Job-Monitor/0.3 career-page reader"},
        )
        source = self._read(request).decode("utf-8", errors="replace")
        values: dict[str, str] = {}
        for key, pattern in _WORKDAY_VALUE_RE.items():
            match = pattern.search(source)
            if not match:
                raise ValueError(f"Workday page is missing {key}: {page_url}")
            values[key] = match.group(1)
        locale_match = _WORKDAY_LOCALE_RE.search(source)
        values["locale"] = locale_match.group(1) if locale_match else "en-US"
        values["origin"] = f"{urlsplit(page_url).scheme}://{urlsplit(page_url).netloc}"
        self._sites[page_url] = values
        return values

    def _search(
        self,
        endpoint: str,
        search_text: str,
        offset: int,
        limit: int,
        applied_facets: Mapping[str, list[str]],
    ) -> Mapping[str, Any]:
        body = json.dumps(
            {
                "appliedFacets": applied_facets,
                "limit": limit,
                "offset": offset,
                "searchText": search_text,
            }
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "LinkedIn-Job-Monitor/0.3 career-page reader",
            },
            method="POST",
        )
        return json.loads(self._read(request).decode("utf-8"))

    def collect_career_job_summaries(
        self,
        page: Mapping[str, str],
        max_cards: int,
        target_roles: list[str],
    ) -> list[Mapping[str, Any]]:
        page_url = page["url"]
        self.last_host_calls = 0
        self.last_collection_truncated = False
        site = self._discover(page_url)
        endpoint = (
            f"{site['origin']}/wday/cxs/{site['tenant']}/{site['siteId']}/jobs"
        )
        detail_base = (
            f"{site['origin']}/{site['locale']}/{site['siteId']}"
        )
        company = _workday_company(page, site["tenant"])
        namespace = _source_namespace(page_url)
        applied_facets = _workday_applied_facets(page_url)
        summaries: list[Mapping[str, Any]] = []
        seen_paths: set[str] = set()

        search_terms = list(dict.fromkeys(target_roles))
        for term_index, search_text in enumerate(search_terms):
            remaining_terms = len(search_terms) - term_index
            role_cap = max(1, (max_cards - len(summaries)) // remaining_terms)
            offset = 0
            role_matched = 0
            total = 0
            pages_read = 0
            while (
                role_matched < role_cap
                and pages_read < _MAX_SEARCH_PAGES_PER_ROLE
            ):
                limit = min(20, max(1, int(total or 20) - offset))
                payload = self._search(
                    endpoint,
                    search_text,
                    offset,
                    limit,
                    applied_facets,
                )
                pages_read += 1
                postings = payload.get("jobPostings") or []
                if not postings:
                    break
                for posting in postings:
                    external_path = str(posting.get("externalPath") or "")
                    if (
                        not external_path
                        or external_path in seen_paths
                        or not _title_matches_target(posting.get("title"), search_text)
                    ):
                        continue
                    seen_paths.add(external_path)
                    summaries.append(
                        {
                            "title": posting.get("title"),
                            "company": company,
                            "location_text": posting.get("locationsText"),
                            "work_mode_text": posting.get("remoteType"),
                            "posted_at_text": posting.get("postedOn"),
                            "job_url": urljoin(detail_base + "/", external_path.lstrip("/")),
                            "job_id": _job_id(posting),
                            "source_namespace": namespace,
                            "source_mode": "career_pages",
                            "career_platform": "workday",
                        }
                    )
                    role_matched += 1
                    if len(summaries) >= max_cards:
                        break
                offset += len(postings)
                total = int(payload.get("total") or 0)
                if offset >= total:
                    break
            if offset < total:
                self.last_collection_truncated = True
            if len(summaries) >= max_cards:
                break
        return summaries

    def extract_job_details(
        self, reference: Any, check_detailed_jd: bool
    ) -> Mapping[str, Any]:
        if not check_detailed_jd:
            return {}
        job_url = (
            str(reference.get("job_url") or "")
            if isinstance(reference, Mapping)
            else str(reference)
        )
        request = Request(
            job_url,
            headers={"User-Agent": "LinkedIn-Job-Monitor/0.3 career-page reader"},
        )
        source = self._read(request).decode("utf-8", errors="replace")
        description = _json_ld_job_description(source)
        if description:
            return {"jd_text": description}
        description_match = _OG_DESCRIPTION_RE.search(source)
        return {
            "jd_text": html.unescape(description_match.group(1))
            if description_match
            else ""
        }


class PublicHtmlCareerSession:
    """Shared read-only HTML behavior for public career sites."""

    platform_name = "public_html"

    def __init__(
        self,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: int = 20,
    ) -> None:
        self._opener = opener
        self.timeout_seconds = timeout_seconds
        self.last_collection_truncated = False
        self.last_host_calls = 0

    def _read_url(self, url: str) -> str:
        self.last_host_calls += 1
        request = Request(
            url,
            headers={"User-Agent": "LinkedIn-Job-Monitor/0.4 career-page reader"},
        )
        with self._opener(request, timeout=self.timeout_seconds) as response:
            return response.read().decode("utf-8", errors="replace")

    def extract_job_details(
        self, reference: Any, check_detailed_jd: bool
    ) -> Mapping[str, Any]:
        if not check_detailed_jd:
            return {}
        job_url = (
            str(reference.get("job_url") or "")
            if isinstance(reference, Mapping)
            else str(reference)
        )
        return {"jd_text": _detail_description(self._read_url(job_url))}


class ScotiabankCareerSession(PublicHtmlCareerSession):
    """Read the public SuccessFactors-rendered Scotiabank result table."""

    platform_name = "successfactors"

    @staticmethod
    def _parse_results(source: str, page_url: str) -> tuple[list[dict[str, Any]], int]:
        rows: list[dict[str, Any]] = []
        for fragment in _SCOTIA_ROW_RE.findall(source):
            title_match = _SCOTIA_TITLE_RE.search(fragment)
            if not title_match:
                continue
            job_url = urljoin(page_url, html.unescape(title_match.group(1)))
            id_match = re.search(r"/(\d+)/?(?:\?.*)?$", urlsplit(job_url).path)
            date_match = _SCOTIA_DATE_RE.search(fragment)
            location_match = _SCOTIA_LOCATION_RE.search(fragment)
            rows.append(
                {
                    "title": _clean_html_text(title_match.group(2)),
                    "location_text": _clean_html_text(
                        location_match.group(1) if location_match else ""
                    ),
                    "posted_at_text": _clean_html_text(
                        date_match.group(1) if date_match else ""
                    ),
                    "job_url": job_url,
                    "job_id": id_match.group(1) if id_match else None,
                }
            )
        total_match = _SCOTIA_TOTAL_RE.search(source)
        total = int(total_match.group(1).replace(",", "")) if total_match else len(rows)
        return rows, total

    def collect_career_job_summaries(
        self,
        page: Mapping[str, str],
        max_cards: int,
        target_roles: list[str],
    ) -> list[Mapping[str, Any]]:
        self.last_host_calls = 0
        self.last_collection_truncated = False
        page_url = page["url"]
        company = str(page.get("company") or "").strip() or "Scotiabank"
        summaries: list[Mapping[str, Any]] = []
        seen_urls: set[str] = set()
        search_terms = list(dict.fromkeys(target_roles))

        for term_index, search_text in enumerate(search_terms):
            remaining_terms = len(search_terms) - term_index
            role_cap = max(1, (max_cards - len(summaries)) // remaining_terms)
            offset = 0
            role_matched = 0
            total = 0
            pages_read = 0
            while (
                role_matched < role_cap
                and pages_read < _MAX_SEARCH_PAGES_PER_ROLE
            ):
                search_url = _query_url(
                    page_url,
                    {"q": search_text, "startrow": offset},
                )
                rows, total = self._parse_results(
                    self._read_url(search_url),
                    page_url,
                )
                pages_read += 1
                if not rows:
                    break
                for row in rows:
                    if (
                        row["job_url"] in seen_urls
                        or not _title_matches_target(row.get("title"), search_text)
                    ):
                        continue
                    seen_urls.add(row["job_url"])
                    summaries.append(
                        {
                            **row,
                            "company": company,
                            "source_namespace": _source_namespace(page_url),
                            "source_mode": "career_pages",
                            "career_platform": self.platform_name,
                        }
                    )
                    role_matched += 1
                    if len(summaries) >= max_cards:
                        break
                offset += len(rows)
                if offset >= total or len(rows) < 25:
                    break
            if offset < total:
                self.last_collection_truncated = True
            if len(summaries) >= max_cards:
                break
        return summaries


class PhenomCareerSession(PublicHtmlCareerSession):
    """Read server-embedded public Phenom search data used by BMO and RBC."""

    platform_name = "phenom"
    _DEFAULT_COMPANIES = {
        "jobs.bmo.com": "BMO",
        "jobs.rbc.com": "RBC",
    }

    @staticmethod
    def _parse_search(source: str) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        app_match = _PHENOM_APP_RE.search(source)
        ddo_match = _PHENOM_DDO_RE.search(source)
        if not app_match or not ddo_match:
            raise ValueError("Phenom page is missing embedded public search data")
        return json.loads(app_match.group(1)), json.loads(ddo_match.group(1))

    @staticmethod
    def _job_url(app: Mapping[str, Any], job: Mapping[str, Any]) -> str:
        sequence = str(job.get("jobSeqNo") or job.get("jobId") or "").strip()
        title = re.sub(r"[^a-z0-9]+", "-", str(job.get("title") or "").lower())
        title = title.strip("-") or "job"
        base_url = str(app.get("baseUrl") or "").rstrip("/") + "/"
        return urljoin(base_url, f"job/{quote(sequence, safe='')}/{quote(title)}")

    def collect_career_job_summaries(
        self,
        page: Mapping[str, str],
        max_cards: int,
        target_roles: list[str],
    ) -> list[Mapping[str, Any]]:
        self.last_host_calls = 0
        self.last_collection_truncated = False
        page_url = page["url"]
        host = urlsplit(page_url).netloc.lower()
        company = (
            str(page.get("company") or "").strip()
            or self._DEFAULT_COMPANIES.get(host, host)
        )
        summaries: list[Mapping[str, Any]] = []
        seen_ids: set[str] = set()
        search_terms = list(dict.fromkeys(target_roles))

        for term_index, search_text in enumerate(search_terms):
            remaining_terms = len(search_terms) - term_index
            role_cap = max(1, (max_cards - len(summaries)) // remaining_terms)
            offset = 0
            role_matched = 0
            total = 0
            pages_read = 0
            while (
                role_matched < role_cap
                and pages_read < _MAX_SEARCH_PAGES_PER_ROLE
            ):
                search_url = _query_url(
                    page_url,
                    {"keywords": search_text, "from": offset},
                )
                app, ddo = self._parse_search(self._read_url(search_url))
                pages_read += 1
                search = ddo.get("eagerLoadRefineSearch") or {}
                data = search.get("data") or {}
                jobs = data.get("jobs") or []
                total = int(search.get("totalHits") or len(jobs))
                if not jobs:
                    break
                for job in jobs:
                    job_id = str(job.get("jobId") or job.get("reqId") or "").strip()
                    identity = job_id or str(job.get("jobSeqNo") or "").strip()
                    if (
                        not identity
                        or identity in seen_ids
                        or not _title_matches_target(job.get("title"), search_text)
                    ):
                        continue
                    seen_ids.add(identity)
                    multi_locations = job.get("multi_location") or []
                    location = (
                        job.get("cityStateCountry")
                        or job.get("location")
                        or ", ".join(str(item) for item in multi_locations)
                    )
                    summaries.append(
                        {
                            "title": job.get("title"),
                            "company": company,
                            "location_text": location,
                            "posted_at_text": job.get("postedDate"),
                            "job_url": self._job_url(app, job),
                            "job_id": job_id or identity,
                            "source_namespace": _source_namespace(page_url),
                            "source_mode": "career_pages",
                            "career_platform": self.platform_name,
                        }
                    )
                    role_matched += 1
                    if len(summaries) >= max_cards:
                        break
                offset += len(jobs)
                if offset >= total:
                    break
            if offset < total:
                self.last_collection_truncated = True
            if len(summaries) >= max_cards:
                break
        return summaries


class BuiltInCareerSession:
    """Dispatch supported public URLs to the matching platform reader."""

    def __init__(
        self,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: int = 20,
    ) -> None:
        self._workday = WorkdayCareerSession(opener, timeout_seconds)
        self._scotiabank = ScotiabankCareerSession(opener, timeout_seconds)
        self._phenom = PhenomCareerSession(opener, timeout_seconds)
        self.last_collection_truncated = False
        self.last_host_calls = 0

    def _adapter(self, url: str, platform: str = "") -> Any:
        host = urlsplit(url).netloc.lower()
        if platform == "workday" or host.endswith(".myworkdayjobs.com"):
            return self._workday
        if platform == "successfactors" or host == "jobs.scotiabank.com":
            return self._scotiabank
        if platform == "phenom" or host in {"jobs.bmo.com", "jobs.rbc.com"}:
            return self._phenom
        raise ValueError(
            f"Unsupported career-page host: {host}. Provide a runtime adapter."
        )

    def collect_career_job_summaries(
        self,
        page: Mapping[str, str],
        max_cards: int,
        target_roles: list[str],
    ) -> list[Mapping[str, Any]]:
        adapter = self._adapter(page["url"])
        summaries = adapter.collect_career_job_summaries(
            page,
            max_cards,
            target_roles,
        )
        self.last_collection_truncated = adapter.last_collection_truncated
        self.last_host_calls = adapter.last_host_calls
        return summaries

    def extract_job_details(
        self, reference: Any, check_detailed_jd: bool
    ) -> Mapping[str, Any]:
        if isinstance(reference, Mapping):
            job_url = str(reference.get("job_url") or "")
            platform = str(reference.get("career_platform") or "")
        else:
            job_url = str(reference)
            platform = ""
        adapter = self._adapter(job_url, platform)
        details = adapter.extract_job_details(reference, check_detailed_jd)
        self.last_host_calls = adapter.last_host_calls
        return details


def resolve_career_session(session: Any | None) -> Any:
    return session if session is not None else BuiltInCareerSession()


def collect_career_job_candidates_report(
    career_pages: list[Mapping[str, str]],
    session: Any,
    target_roles: list[str],
    max_cards_per_page: int = 100,
) -> CandidateFetchResult:
    """Collect card summaries across company pages without requiring LinkedIn settings."""
    stats = FetchStats(
        collection_mode="career_page_summaries",
        pages_configured=len(career_pages),
    )
    candidates: list[JobCandidate] = []
    started = perf_counter()
    for page in career_pages:
        try:
            collect = getattr(session, "collect_career_job_summaries", None)
            if callable(collect):
                summaries = collect(page, max_cards_per_page, target_roles)
            else:
                session.goto(page["url"])
                summaries = session.collect_job_summaries(max_cards_per_page)
            stats.summary_host_calls += int(getattr(session, "last_host_calls", 1))
            stats.truncated = stats.truncated or bool(
                getattr(session, "last_collection_truncated", False)
            )
        except Exception as exc:
            stats.fetch_errors += 1
            stats.pages_failed += 1
            stats.page_errors[page["url"]] = f"{type(exc).__name__}: {exc}"
            continue

        stats.pages_succeeded += 1
        stats.cards_collected += len(summaries)
        namespace = career_source_namespace(page["url"])
        company = str(page.get("company") or "").strip()
        for summary in summaries[:max_cards_per_page]:
            stats.cards_attempted += 1
            values = {
                **summary,
                "company": summary.get("company") or company,
                "source_namespace": summary.get("source_namespace") or namespace,
                "source_mode": "career_pages",
            }
            if values.get("requisition_id") and not values.get("job_id"):
                values["job_id"] = values["requisition_id"]
            try:
                raw = _raw_from_mapping(values, check_detailed_jd=False)
            except Exception:
                stats.parse_failed += 1
                continue
            if not (raw.title and raw.company and raw.job_url):
                stats.parse_failed += 1
                continue
            candidates.append(
                JobCandidate(raw=raw, detail_reference=values, details_loaded=False)
            )
            stats.jobs_parsed += 1

    stats.summary_duration_ms = round((perf_counter() - started) * 1000, 3)
    stats.collection_complete = (
        not stats.truncated
        and stats.pages_failed == 0
        and stats.parse_failed == 0
        and stats.pages_succeeded == stats.pages_configured
    )
    if stats.pages_failed == stats.pages_configured and stats.pages_configured:
        stats.fatal_error = "All configured career pages failed"
    return CandidateFetchResult(candidates=candidates, stats=stats)
