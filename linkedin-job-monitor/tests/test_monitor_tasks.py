from __future__ import annotations

import unittest
from unittest.mock import patch

from monitor_tasks import (
    create_monitor_task,
    format_monitor_task_overview,
    get_monitor_task,
    group_monitor_tasks,
    migrate_single_profile_to_registry,
    remove_monitor_task,
    run_monitor_tasks,
    set_monitor_task_enabled,
    update_monitor_task,
    validate_task_registry,
)


def linkedin_profile() -> dict:
    return {
        "source_mode": "linkedin",
        "search_url": "https://www.linkedin.com/jobs/search/?keywords=marketing",
        "target_roles": ["marketing analyst", "marketing manager"],
        "regions": ["greater toronto area"],
        "allowed_location_types": ["hybrid", "remote"],
    }


def career_profile(company: str, url: str, roles: list[str]) -> dict:
    return {
        "source_mode": "career_pages",
        "career_pages": [{"company": company, "url": url}],
        "target_roles": roles,
        "regions": ["greater toronto area"],
    }


class FakeCareerSession:
    def collect_career_job_summaries(
        self, page: dict[str, str], max_cards: int, target_roles: list[str]
    ) -> list[dict]:
        role = target_roles[0]
        return [
            {
                "title": role.title(),
                "company": page["company"],
                "location_text": "Toronto, Ontario, Canada",
                "job_url": f"{page['url']}/job/{page['company']}-1",
                "job_id": f"{page['company']}-1",
            }
        ]


class MonitorTaskTest(unittest.TestCase):
    def test_overview_groups_linkedin_and_career_tasks(self) -> None:
        registry = create_monitor_task(
            None,
            "LinkedIn marketing",
            linkedin_profile(),
            task_id="linkedin-marketing",
        )
        registry = create_monitor_task(
            registry,
            "BMO risk",
            {
                **career_profile(
                    "BMO",
                    "https://jobs.bmo.com/ca/en/search-results",
                    ["risk analyst", "risk manager"],
                ),
                "jd_must_have_keywords": ["risk governance", "sql"],
            },
            task_id="bmo-risk",
        )

        grouped = group_monitor_tasks(registry)
        self.assertEqual(len(grouped["linkedin"]), 1)
        self.assertEqual(len(grouped["career_pages"]), 1)
        overview = format_monitor_task_overview(registry)
        self.assertIn("LinkedIn 搜索（1）", overview)
        self.assertIn("单独配置的 Career 页面（1）", overview)
        self.assertIn("risk analyst, risk manager", overview)
        self.assertIn("必须词: risk governance, sql", overview)

    def test_task_updates_preserve_fields_and_enable_new_jd_rules(self) -> None:
        registry = create_monitor_task(
            None,
            "TD marketing",
            career_profile(
                "TD",
                "https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers",
                ["marketing manager"],
            ),
            task_id="td-marketing",
        )
        self.assertFalse(
            get_monitor_task(registry, "td-marketing")["profile"]["check_detailed_jd"]
        )

        registry = update_monitor_task(
            registry,
            "td-marketing",
            {"jd_must_have_keywords": ["campaign measurement"]},
        )
        task = get_monitor_task(registry, "td-marketing")
        self.assertTrue(task["profile"]["check_detailed_jd"])
        self.assertEqual(task["profile"]["target_roles"], ["marketing manager"])

    def test_generated_ids_enable_disable_and_remove_tasks(self) -> None:
        registry = create_monitor_task(None, "BMO Risk", career_profile(
            "BMO", "https://jobs.bmo.com/ca/en/search-results", ["risk analyst"]
        ))
        registry = create_monitor_task(registry, "BMO Risk", career_profile(
            "BMO", "https://bmo.wd3.myworkdayjobs.com/External", ["risk manager"]
        ))
        self.assertEqual(
            [task["task_id"] for task in registry["tasks"]],
            ["bmo-risk", "bmo-risk-2"],
        )
        registry = set_monitor_task_enabled(registry, "bmo-risk-2", False)
        self.assertFalse(get_monitor_task(registry, "bmo-risk-2")["enabled"])
        registry = remove_monitor_task(registry, "bmo-risk-2")
        self.assertEqual(len(registry["tasks"]), 1)

    def test_legacy_profile_and_state_migrate_without_losing_records(self) -> None:
        old_state = {"records": {"jobid::123": {"lifecycle_status": "active"}}}
        registry, state = migrate_single_profile_to_registry(
            linkedin_profile(), old_state, task_id="legacy-linkedin"
        )

        self.assertEqual(registry["tasks"][0]["task_id"], "legacy-linkedin")
        self.assertIn("jobid::123", state["task_states"]["legacy-linkedin"]["records"])

    def test_batch_runner_selects_multiple_tasks_and_separates_state(self) -> None:
        registry = create_monitor_task(
            None,
            "TD marketing",
            career_profile(
                "TD",
                "https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers",
                ["marketing manager"],
            ),
            task_id="td-marketing",
        )
        registry = create_monitor_task(
            registry,
            "BMO risk",
            career_profile(
                "BMO",
                "https://jobs.bmo.com/ca/en/search-results",
                ["risk analyst", "risk manager"],
            ),
            task_id="bmo-risk",
        )
        registry = create_monitor_task(
            registry,
            "RBC disabled",
            career_profile(
                "RBC",
                "https://jobs.rbc.com/ca/en/search-results",
                ["financial analyst"],
            ),
            task_id="rbc-disabled",
            enabled=False,
        )
        sessions = {
            "td-marketing": FakeCareerSession(),
            "bmo-risk": FakeCareerSession(),
        }

        digest, state = run_monitor_tasks(registry, {}, sessions=sessions)

        stats = state["last_batch_stats"]
        self.assertEqual(stats["tasks_selected"], 3)
        self.assertEqual(stats["tasks_succeeded"], 2)
        self.assertEqual(stats["tasks_skipped_disabled"], 1)
        self.assertEqual(stats["notified"], 2)
        self.assertEqual(set(state["task_states"]), {"td-marketing", "bmo-risk"})
        self.assertIn("## TD marketing (`td-marketing`)", digest)
        self.assertIn("## BMO risk (`bmo-risk`)", digest)

    def test_linkedin_failure_does_not_erase_successful_career_task(self) -> None:
        registry = create_monitor_task(
            None,
            "LinkedIn marketing",
            linkedin_profile(),
            task_id="linkedin-marketing",
        )
        registry = create_monitor_task(
            registry,
            "CIBC marketing",
            career_profile(
                "CIBC",
                "https://cibc.wd3.myworkdayjobs.com/search",
                ["marketing manager"],
            ),
            task_id="cibc-marketing",
        )

        _, state = run_monitor_tasks(
            registry,
            {},
            sessions={"cibc-marketing": FakeCareerSession()},
        )

        stats = state["last_batch_stats"]
        self.assertEqual(stats["tasks_succeeded"], 1)
        self.assertEqual(stats["tasks_failed"], 1)
        self.assertIn("cibc-marketing", state["task_states"])
        self.assertNotIn("linkedin-marketing", state["task_states"])

    def test_registry_rejects_duplicate_ids(self) -> None:
        registry = create_monitor_task(
            None, "One", linkedin_profile(), task_id="same-id"
        )
        registry["tasks"].append(dict(registry["tasks"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate task_id"):
            validate_task_registry(registry)

    def test_failed_task_does_not_mutate_its_previous_state(self) -> None:
        registry = create_monitor_task(
            None, "LinkedIn", linkedin_profile(), task_id="linkedin"
        )
        previous = {
            "task_states": {"linkedin": {"records": {"keep": {"status": "active"}}}}
        }

        def failing_run(profile: dict, state: dict, **kwargs: object) -> tuple[str, dict]:
            state["records"].clear()
            raise RuntimeError("temporary failure")

        with patch("monitor_tasks.run_monitor", side_effect=failing_run):
            _, updated = run_monitor_tasks(registry, previous, sessions={"linkedin": object()})

        self.assertIn("keep", updated["task_states"]["linkedin"]["records"])

    def test_task_selection_requires_a_string_list(self) -> None:
        registry = create_monitor_task(
            None, "LinkedIn", linkedin_profile(), task_id="linkedin"
        )
        with self.assertRaisesRegex(ValueError, "task_ids must be a list"):
            run_monitor_tasks(registry, {}, task_ids="linkedin")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
