from __future__ import annotations

import unittest

from config_schema import ProfileValidationError, validate_profile
from run_monitor import run_monitor


class FakeSession:
    def __init__(self) -> None:
        self.jd_reads = 0

    def goto(self, url: str) -> None:
        pass

    def collect_job_cards(self) -> list[object]:
        return [object()]

    def open_job_card(self, card: object) -> None:
        pass

    def extract_visible_text(self, selector: str) -> str | None:
        if selector == ".jobs-description-content__text":
            self.jd_reads += 1
            return "Python"
        return {
            ".job-details-jobs-unified-top-card__job-title": "Data Analyst",
            ".job-details-jobs-unified-top-card__company-name": "Example Co",
            ".job-details-jobs-unified-top-card__bullet": "Toronto, Ontario",
            ".jobs-unified-top-card__workplace-type": "Hybrid",
        }.get(selector)

    def extract_attr(self, selector: str, attr: str) -> str | None:
        if attr == "href":
            return "https://www.linkedin.com/jobs/view/123"
        if attr == "data-job-id":
            return "123"
        return None


def make_profile(**updates: object) -> dict:
    raw = {
        "search_url": "https://www.linkedin.com/jobs/search/?keywords=data",
        "target_roles": ["data analyst"],
        "regions": ["ontario"],
        "allowed_location_types": ["hybrid"],
        "jd_must_have_keywords": ["sql"],
    }
    raw.update(updates)
    return validate_profile(raw)


class MonitorOptionsTest(unittest.TestCase):
    def test_detailed_jd_can_be_skipped(self) -> None:
        session = FakeSession()
        digest, _ = run_monitor(make_profile(check_detailed_jd=False), {}, session)

        self.assertEqual(session.jd_reads, 0)
        self.assertIn("[match] Data Analyst", digest)

    def test_matches_only_omits_a_job_that_fails_jd_filter(self) -> None:
        digest, _ = run_monitor(make_profile(), {}, FakeSession())

        self.assertIn("shown=0", digest)
        self.assertNotIn("Data Analyst — Example Co", digest)

    def test_partial_mode_labels_and_explains_rejected_job(self) -> None:
        digest, state = run_monitor(
            make_profile(output_mode="include_partial_matches"), {}, FakeSession()
        )

        self.assertIn("[partial match] Data Analyst — Example Co", digest)
        self.assertIn("jd_missing_must_have_keywords", digest)

        # A partial result becoming a full match must not be hidden as already seen.
        follow_up, _ = run_monitor(
            make_profile(check_detailed_jd=False, output_mode="matches_only"),
            state,
            FakeSession(),
        )
        self.assertIn("[match] Data Analyst — Example Co", follow_up)

    def test_output_mode_is_validated(self) -> None:
        with self.assertRaises(ProfileValidationError):
            make_profile(output_mode="everything")


if __name__ == "__main__":
    unittest.main()
