from __future__ import annotations

import io
import json
import unittest

from collect_profile import merge_profile_update, profile_exists, required_setup_fields
from config_schema import ProfileValidationError, validate_profile
from fetch_career_jobs import (
    BuiltInCareerSession,
    PhenomCareerSession,
    ScotiabankCareerSession,
    WorkdayCareerSession,
)
from run_monitor import run_monitor


TD_URL = "https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers"
CIBC_URL = "https://cibc.wd3.myworkdayjobs.com/search"
BMO_WORKDAY_URL = (
    "https://bmo.wd3.myworkdayjobs.com/External?"
    "timeType=full-time-id&Country=canada-id"
)
BMO_PHENOM_URL = "https://jobs.bmo.com/ca/en/search-results?keywords=risk"
RBC_URL = "https://jobs.rbc.com/ca/en/search-results?keywords=analyst"
SCOTIA_URL = (
    "https://jobs.scotiabank.com/search/?createNewAlert=false&"
    "q=marketing&locationsearch="
)


def career_profile(**updates: object) -> dict:
    values = {
        "source_mode": "career_pages",
        "career_pages": [
            {"company": "TD", "url": TD_URL},
            {"company": "CIBC", "url": CIBC_URL},
        ],
        "target_roles": ["marketing manager"],
        "regions": ["greater toronto area"],
    }
    values.update(updates)
    return validate_profile(values)


class FakeCareerSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def collect_career_job_summaries(
        self, page: dict[str, str], max_cards: int, target_roles: list[str]
    ) -> list[dict]:
        self.calls.append(page["url"])
        company = page["company"]
        return [
            {
                "title": "Senior Manager, Marketing",
                "company": company,
                "location_text": "Toronto, ON",
                "work_mode_text": "Hybrid",
                "posted_at_text": "Posted 2 Days Ago",
                "job_url": f"{page['url']}/job/marketing_REQ-1",
                "job_id": "REQ-1",
            }
        ]


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class FakeWorkdayOpener:
    def __init__(self) -> None:
        self.requests = []

    def __call__(self, request: object, timeout: int) -> FakeResponse:
        self.requests.append(request)
        data = getattr(request, "data", None)
        url = getattr(request, "full_url")
        if data is not None:
            payload = {
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Senior Manager, Marketing",
                        "externalPath": "/job/Toronto-ON/Senior-Manager--Marketing_REQ-7",
                        "locationsText": "Toronto, ON",
                        "postedOn": "Posted 2 Days Ago",
                        "remoteType": "Hybrid",
                        "bulletFields": ["REQ-7"],
                    }
                ],
            }
            return FakeResponse(json.dumps(payload).encode())
        if "/job/" in url:
            posting = {
                "@type": "JobPosting",
                "description": "Pay Details: $50 per hour. Build campaigns.",
            }
            body = (
                '<script type="application/ld+json">'
                + json.dumps(posting)
                + "</script>"
            )
            return FakeResponse(body.encode())
        landing = (
            '<script>window.workday = {tenant: "td", siteId: '
            '"TD_Bank_Careers", locale: "en-US"};</script>'
        )
        return FakeResponse(landing.encode())


class CareerPageModeTest(unittest.TestCase):
    def test_career_mode_has_a_smaller_required_setup(self) -> None:
        self.assertEqual(required_setup_fields(), ["source_mode"])
        self.assertEqual(
            required_setup_fields("career_pages"),
            ["career_pages", "target_roles", "regions"],
        )
        profile = career_profile()
        self.assertTrue(profile_exists(profile))
        self.assertFalse(profile["check_detailed_jd"])
        self.assertEqual(
            profile["allowed_location_types"],
            ["remote", "hybrid", "onsite", "unknown"],
        )
        self.assertTrue(
            career_profile(minimum_salary_cad=100000)["check_detailed_jd"]
        )

    def test_career_mode_requires_https_pages_but_not_linkedin_url(self) -> None:
        with self.assertRaises(ProfileValidationError):
            career_profile(career_pages=["http://example.com/jobs"])
        self.assertEqual(career_profile()["search_url"], "")

    def test_switching_modes_applies_the_simple_career_default(self) -> None:
        linkedin = validate_profile(
            {
                "search_url": "https://www.linkedin.com/jobs/search/?keywords=data",
                "target_roles": ["data analyst"],
                "regions": ["ontario"],
                "allowed_location_types": ["hybrid"],
            }
        )
        switched = merge_profile_update(
            linkedin,
            {
                "source_mode": "career_pages",
                "career_pages": [TD_URL],
                "target_roles": ["marketing manager"],
            },
        )
        self.assertFalse(switched["check_detailed_jd"])

    def test_multiple_company_pages_use_namespaced_job_ids(self) -> None:
        session = FakeCareerSession()
        digest, state = run_monitor(career_profile(), {}, session)

        self.assertEqual(session.calls, [TD_URL, CIBC_URL])
        self.assertIn("Career-page monitor digest", digest)
        self.assertIn("TD", digest)
        self.assertIn("CIBC", digest)
        self.assertEqual(state["last_run_stats"]["pages_succeeded"], 2)
        self.assertEqual(state["last_run_stats"]["notified"], 2)
        self.assertIn(
            "career::td.wd3.myworkdayjobs.com/td_bank_careers::jobid::req-1",
            state["records"],
        )
        self.assertIn(
            "career::cibc.wd3.myworkdayjobs.com/search::jobid::req-1",
            state["records"],
        )

    def test_career_title_and_gta_filters_run_from_cards(self) -> None:
        class MixedSession(FakeCareerSession):
            def collect_career_job_summaries(
                self, page: dict[str, str], max_cards: int, target_roles: list[str]
            ) -> list[dict]:
                rows = super().collect_career_job_summaries(
                    page, max_cards, target_roles
                )
                if page["company"] == "CIBC":
                    rows[0]["title"] = "Risk Analyst"
                    rows[0]["location_text"] = "Vancouver, BC"
                return rows

        _, state = run_monitor(career_profile(), {}, MixedSession())

        stats = state["last_run_stats"]
        self.assertEqual(stats["matched"], 1)
        self.assertEqual(stats["rejected"], 1)
        self.assertEqual(stats["detail_fetch_attempted"], 0)
        self.assertEqual(stats["rejection_reasons"]["target_role_mismatch"], 1)

    def test_workday_client_discovers_search_and_detail_data(self) -> None:
        opener = FakeWorkdayOpener()
        session = WorkdayCareerSession(opener=opener)
        summaries = session.collect_career_job_summaries(
            {"company": "TD", "url": TD_URL},
            max_cards=10,
            target_roles=["marketing manager"],
        )

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["job_id"], "REQ-7")
        self.assertEqual(summaries[0]["location_text"], "Toronto, ON")
        self.assertIn("/en-US/TD_Bank_Careers/job/", summaries[0]["job_url"])
        details = session.extract_job_details(summaries[0], True)
        self.assertIn("$50 per hour", details["jd_text"])

    def test_workday_preserves_url_facets_in_public_search(self) -> None:
        opener = FakeWorkdayOpener()
        session = WorkdayCareerSession(opener=opener)
        session.collect_career_job_summaries(
            {"company": "BMO", "url": BMO_WORKDAY_URL},
            max_cards=10,
            target_roles=["risk"],
        )

        search_request = next(
            request for request in opener.requests if getattr(request, "data", None)
        )
        body = json.loads(search_request.data.decode())
        self.assertEqual(
            body["appliedFacets"],
            {"timeType": ["full-time-id"], "Country": ["canada-id"]},
        )
        self.assertEqual(body["searchText"], "risk")

    def test_scotiabank_result_table_and_detail_are_supported(self) -> None:
        search_html = """
        <span class="paginationLabel">Results <b>1 - 1</b> of <b>1</b></span>
        <table><tr class="data-row">
          <td class="colTitle"><a href="/job/Toronto-Manager/604550117/"
            class="jobTitle-link">Manager, Marketing Analytics</a></td>
          <td class="colDate hidden-phone"><span>Aug 15, 2026</span></td>
          <td class="colLocation hidden-phone"><span>Toronto, ON, CA</span></td>
        </tr></table>
        """
        detail_html = """
        <span itemprop="description"><div>Salary: $50 per hour.</div>
        <p>Build marketing analytics.</p></span>
        """

        def opener(request: object, timeout: int) -> FakeResponse:
            url = getattr(request, "full_url")
            body = detail_html if "/job/" in url else search_html
            return FakeResponse(body.encode())

        session = ScotiabankCareerSession(opener=opener)
        summaries = session.collect_career_job_summaries(
            {"company": "Scotiabank", "url": SCOTIA_URL},
            max_cards=10,
            target_roles=["marketing analytics"],
        )

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["job_id"], "604550117")
        self.assertEqual(summaries[0]["location_text"], "Toronto, ON, CA")
        self.assertEqual(summaries[0]["source_namespace"], "bank/scotiabank")
        details = session.extract_job_details(summaries[0], True)
        self.assertIn("$50 per hour", details["jd_text"])

    def test_phenom_bmo_and_rbc_embedded_search_data_are_supported(self) -> None:
        def phenom_html(base_url: str, ref_num: str, job_id: str) -> str:
            app = {"baseUrl": base_url, "refNum": ref_num}
            ddo = {
                "eagerLoadRefineSearch": {
                    "totalHits": 1,
                    "data": {
                        "jobs": [
                            {
                                "title": "Risk Analyst",
                                "jobId": job_id,
                                "jobSeqNo": f"{ref_num}{job_id}EXTERNALENCA",
                                "cityStateCountry": "Toronto, Ontario, Canada",
                                "postedDate": "2026-08-15T00:00:00.000+0000",
                            }
                        ]
                    },
                }
            }
            return (
                "<script>var phApp = phApp || "
                + json.dumps(app)
                + "; phApp.ddo = "
                + json.dumps(ddo)
                + "; phApp.experimentData = {};</script>"
            )

        def opener(request: object, timeout: int) -> FakeResponse:
            url = getattr(request, "full_url")
            if "jobs.bmo.com" in url:
                source = phenom_html(
                    "https://jobs.bmo.com/ca/en/", "BOMOGLOBAL", "R26001"
                )
            else:
                source = phenom_html(
                    "https://jobs.rbc.com/ca/en/", "RBCAA0088", "R-00001"
                )
            return FakeResponse(source.encode())

        session = PhenomCareerSession(opener=opener)
        bmo = session.collect_career_job_summaries(
            {"company": "BMO", "url": BMO_PHENOM_URL}, 10, ["risk analyst"]
        )
        rbc = session.collect_career_job_summaries(
            {"company": "RBC", "url": RBC_URL}, 10, ["risk analyst"]
        )

        self.assertEqual(bmo[0]["source_namespace"], "bank/bmo")
        self.assertEqual(rbc[0]["source_namespace"], "bank/rbc")
        self.assertIn("/ca/en/job/BOMOGLOBALR26001EXTERNALENCA/", bmo[0]["job_url"])
        self.assertEqual(rbc[0]["job_id"], "R-00001")

    def test_bmo_dual_entry_urls_dedupe_on_the_same_job_id(self) -> None:
        class DualBmoSession:
            def collect_career_job_summaries(
                self,
                page: dict[str, str],
                max_cards: int,
                target_roles: list[str],
            ) -> list[dict]:
                return [
                    {
                        "title": "Risk Analyst",
                        "company": "BMO",
                        "location_text": "Toronto, Ontario, Canada",
                        "job_url": f"{page['url']}/job/R26001",
                        "job_id": "R26001",
                        "source_namespace": "bank/bmo",
                    }
                ]

        profile = career_profile(
            career_pages=[
                {"company": "BMO", "url": BMO_WORKDAY_URL},
                {"company": "BMO", "url": BMO_PHENOM_URL},
            ],
            target_roles=["risk analyst"],
        )
        _, state = run_monitor(profile, {}, DualBmoSession())

        self.assertEqual(state["last_run_stats"]["duplicate_cards_skipped"], 1)
        self.assertEqual(state["last_run_stats"]["notified"], 1)
        self.assertIn("career::bank/bmo::jobid::r26001", state["records"])

    def test_built_in_dispatcher_rejects_unknown_platforms_clearly(self) -> None:
        session = BuiltInCareerSession(opener=FakeWorkdayOpener())
        with self.assertRaisesRegex(ValueError, "Unsupported career-page host"):
            session.collect_career_job_summaries(
                {"company": "Example", "url": "https://example.com/jobs"},
                10,
                ["analyst"],
            )

    def test_partial_page_failure_does_not_expire_other_company_jobs(self) -> None:
        _, state = run_monitor(career_profile(), {}, FakeCareerSession())

        class PartialFailureSession(FakeCareerSession):
            def collect_career_job_summaries(
                self, page: dict[str, str], max_cards: int, target_roles: list[str]
            ) -> list[dict]:
                if page["company"] == "CIBC":
                    raise RuntimeError("temporary page failure")
                return super().collect_career_job_summaries(
                    page, max_cards, target_roles
                )

        _, state = run_monitor(career_profile(), state, PartialFailureSession())

        stats = state["last_run_stats"]
        self.assertFalse(stats["collection_complete"])
        self.assertEqual(stats["pages_failed"], 1)
        self.assertIn(CIBC_URL, stats["page_errors"])
        cibc_key = "career::cibc.wd3.myworkdayjobs.com/search::jobid::req-1"
        self.assertEqual(state["records"][cibc_key]["lifecycle_status"], "active")


if __name__ == "__main__":
    unittest.main()
