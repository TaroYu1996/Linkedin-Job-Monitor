from __future__ import annotations

import unittest

from apply_filters import apply_hard_filters
from config_schema import ProfileValidationError, validate_profile
from dedupe_jobs import dedupe_jobs, list_job_statuses
from feedback_learning import feedback_adjustment, record_feedback_by_key, record_job_feedback
from fetch_linkedin_jobs import RawLinkedInJob, fetch_linkedin_jobs_report
from normalize_jobs import normalize_jobs
from run_monitor import run_monitor


def raw_job(**updates: object) -> RawLinkedInJob:
    values = {
        "title": "Digital Marketing Manager",
        "company": "Example Co",
        "location_text": "Toronto, Ontario, Canada",
        "work_mode_text": "Hybrid",
        "salary_text": None,
        "posted_at_text": "1 day ago",
        "job_url": "https://www.linkedin.com/jobs/view/123?trk=search",
        "job_id": "123",
        "jd_text": "Salary range: $40-$50 per hour. Lead paid media strategy.",
    }
    values.update(updates)
    return RawLinkedInJob(**values)  # type: ignore[arg-type]


def profile(**updates: object) -> dict:
    values = {
        "search_url": "https://www.linkedin.com/jobs/search/?keywords=marketing",
        "target_roles": ["digital marketing manager"],
        "regions": ["greater toronto area"],
        "allowed_location_types": ["hybrid"],
        "check_detailed_jd": True,
    }
    values.update(updates)
    return validate_profile(values)


class StaticSession:
    def goto(self, url: str) -> None:
        pass

    def collect_job_cards(self) -> list[object]:
        return [object()]

    def open_job_card(self, card: object) -> None:
        pass

    def extract_job_card_metadata(self, card: object) -> dict:
        return {"posted_at_text": "1 day ago"}

    def extract_visible_text(self, selector: str) -> str | None:
        return {
            ".job-details-jobs-unified-top-card__job-title": "Digital Marketing Manager",
            ".job-details-jobs-unified-top-card__company-name": "Example Co",
            ".job-details-jobs-unified-top-card__bullet": "Markham, Ontario, Canada",
            ".jobs-unified-top-card__workplace-type": "Hybrid",
            ".jobs-description-content__text": "Compensation is $6,000 per month.",
        }.get(selector)

    def extract_attr(self, selector: str, attr: str) -> str | None:
        return "https://www.linkedin.com/jobs/view/123" if attr == "href" else "123"


class BrokenCardSession(StaticSession):
    def extract_visible_text(self, selector: str) -> str | None:
        if selector == ".job-details-jobs-unified-top-card__job-title":
            return None
        return super().extract_visible_text(selector)


class FastPathSession(StaticSession):
    def __init__(self) -> None:
        self.details_calls = 0
        self.selector_calls = 0

    def extract_job_details(self, card: object, check_detailed_jd: bool) -> dict:
        self.details_calls += 1
        return {
            "title": "Digital Marketing Manager",
            "company": "Example Co",
            "location_text": "Toronto, Ontario, Canada",
            "work_mode_text": "Hybrid",
            "salary_text": "$80,000 per year",
            "posted_at_text": "1 day ago",
            "job_url": "https://www.linkedin.com/jobs/view/123",
            "job_id": "123",
            "jd_text": "Paid media",
        }

    def extract_visible_text(self, selector: str) -> str | None:
        self.selector_calls += 1
        return super().extract_visible_text(selector)


class EnhancementTest(unittest.TestCase):
    def test_required_profile_lists_cannot_be_empty(self) -> None:
        with self.assertRaises(ProfileValidationError):
            profile(target_roles=[])

    def test_hourly_salary_from_jd_is_annualized(self) -> None:
        job = normalize_jobs([raw_job()], ["greater toronto area"], profile())[0]

        self.assertEqual(job.salary_min_cad, 83200)
        self.assertEqual(job.salary_max_cad, 104000)
        self.assertEqual(job.salary_period, "hour")
        self.assertEqual(job.salary_source, "jd")

    def test_monthly_salary_from_jd_is_annualized(self) -> None:
        job = normalize_jobs(
            [raw_job(jd_text="Compensation: CAD $6,000-$7,000 per month")],
            ["greater toronto area"],
            profile(),
        )[0]

        self.assertEqual(job.salary_min_cad, 72000)
        self.assertEqual(job.salary_max_cad, 84000)
        self.assertEqual(job.salary_period, "month")

    def test_cad_suffix_salary_without_dollar_sign_is_parsed(self) -> None:
        job = normalize_jobs(
            [raw_job(jd_text="Compensation: 80,000-95,000 CAD annually")],
            ["greater toronto area"],
            profile(),
        )[0]

        self.assertEqual(job.salary_min_cad, 80000)
        self.assertEqual(job.salary_max_cad, 95000)

    def test_gta_aliases_and_fuzzy_city_match(self) -> None:
        jobs = normalize_jobs(
            [
                raw_job(location_text="Toronto, Ontario, Canada", job_id="1"),
                raw_job(location_text="Markham, ON", job_id="2"),
                raw_job(location_text="Markhm, Ontario", job_id="3"),
                raw_job(location_text="Montreal, Quebec", job_id="4"),
            ],
            ["greater toronto area"],
            profile(),
        )

        self.assertEqual([job.normalized_region for job in jobs[:3]], ["greater toronto area"] * 3)
        self.assertEqual(jobs[2].region_match_method, "fuzzy")
        self.assertEqual(jobs[3].normalized_region, "unknown")
        rejected = apply_hard_filters([jobs[3]], profile()).rejected
        self.assertIn("region_unknown", rejected[0][1])

    def test_seniority_is_optional_and_only_filters_when_configured(self) -> None:
        job = normalize_jobs([raw_job()], ["greater toronto area"], profile())[0]
        self.assertEqual(job.seniority_hint, "manager")
        self.assertEqual(apply_hard_filters([job], profile()).passed, [job])
        self.assertIn(
            "seniority_mismatch",
            apply_hard_filters([job], profile(seniority=["director"])).rejected[0][1],
        )

    def test_dedupe_prefers_job_id_over_tracking_url(self) -> None:
        jobs = normalize_jobs(
            [raw_job(job_url="https://www.linkedin.com/jobs/view/123?trk=one")],
            ["greater toronto area"],
            profile(),
        )
        first, state = dedupe_jobs(jobs, {}, 14)
        second_jobs = normalize_jobs(
            [raw_job(job_url="https://www.linkedin.com/jobs/view/123?trk=two")],
            ["greater toronto area"],
            profile(),
        )
        second, _ = dedupe_jobs(second_jobs, state, 14)

        self.assertEqual(first[0].dedupe_key, "jobid::123")
        self.assertEqual(second[0].status, "seen")

    def test_missing_jobs_become_expired_after_configured_complete_runs(self) -> None:
        jobs = normalize_jobs([raw_job()], ["greater toronto area"], profile())
        _, state = dedupe_jobs(jobs, {}, 14, expire_after_missing_runs=2)
        _, state = dedupe_jobs([], state, 14, expire_after_missing_runs=2, track_missing=True)
        record = state["records"]["jobid::123"]
        self.assertEqual(record["lifecycle_status"], "missing")

        _, state = dedupe_jobs([], state, 14, expire_after_missing_runs=2, track_missing=True)
        self.assertEqual(record["lifecycle_status"], "expired")
        self.assertEqual(state["last_newly_expired_count"], 1)
        self.assertEqual(list_job_statuses(state, "expired")[0]["linkedin_job_id"], "123")

    def test_feedback_changes_ranking_without_becoming_a_hard_filter(self) -> None:
        liked_job = normalize_jobs([raw_job()], ["greater toronto area"], profile())[0]
        state: dict = {}
        record_job_feedback(state, liked_job, "liked")
        similar_job = normalize_jobs(
            [raw_job(job_id="456", title="Performance Marketing Manager")],
            ["greater toronto area"],
            profile(),
        )[0]

        adjustment, reasons = feedback_adjustment(similar_job, state)
        self.assertGreater(adjustment, 0)
        self.assertIn("feedback_company", reasons)

    def test_feedback_can_be_recorded_later_by_linkedin_job_id(self) -> None:
        job = normalize_jobs([raw_job()], ["greater toronto area"], profile())[0]
        _, state = dedupe_jobs([job], {}, 14)
        record_feedback_by_key(state, "123", "applied")

        status = list_job_statuses(state)[0]
        self.assertEqual(status["user_status"], "applied")

    def test_run_persists_funnel_stats(self) -> None:
        digest, state = run_monitor(profile(minimum_salary_cad=70000), {}, StaticSession())
        stats = state["last_run_stats"]

        self.assertEqual(stats["cards_collected"], 1)
        self.assertEqual(stats["jobs_parsed"], 1)
        self.assertEqual(stats["matched"], 1)
        self.assertEqual(stats["notified"], 1)
        self.assertIn("Funnel:", digest)
        self.assertIn("CAD 72,000/year", digest)

    def test_adapter_fast_path_avoids_selector_round_trips(self) -> None:
        session = FastPathSession()
        result = fetch_linkedin_jobs_report("search", session)

        self.assertEqual(result.stats.jobs_parsed, 1)
        self.assertEqual(session.details_calls, 1)
        self.assertEqual(session.selector_calls, 0)

    def test_parse_failure_does_not_advance_missing_lifecycle(self) -> None:
        _, state = run_monitor(profile(), {}, StaticSession())
        _, state = run_monitor(profile(), state, BrokenCardSession())

        self.assertFalse(state["last_run_stats"]["collection_complete"])
        self.assertEqual(state["last_run_stats"]["parse_failed"], 1)
        self.assertEqual(state["records"]["jobid::123"]["lifecycle_status"], "active")

    def test_applicant_count_is_not_reported_as_clicked_apply(self) -> None:
        job = normalize_jobs(
            [raw_job(apply_click_count_text="100+ applicants")],
            ["greater toronto area"],
            profile(),
        )[0]
        self.assertIsNone(job.apply_click_count)


if __name__ == "__main__":
    unittest.main()
