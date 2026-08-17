"""Manage and run multiple independent LinkedIn or career-page monitor tasks."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Mapping

from collect_profile import merge_profile_update
from config_schema import validate_profile
from run_monitor import run_monitor


TASK_REGISTRY_VERSION = 1
_TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_JD_FIELDS = (
    "jd_include_keywords",
    "jd_must_have_keywords",
    "jd_exclude_keywords",
)


def _empty_registry() -> dict[str, Any]:
    return {"version": TASK_REGISTRY_VERSION, "tasks": []}


def _task_id_from_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (value or "monitor-task")[:64].rstrip("-")


def validate_task_registry(registry: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate task metadata and every nested monitor profile."""
    if registry is None:
        return _empty_registry()
    if not isinstance(registry, Mapping):
        raise ValueError("task registry must be a mapping")
    version = registry.get("version", TASK_REGISTRY_VERSION)
    if version != TASK_REGISTRY_VERSION:
        raise ValueError(f"unsupported task registry version: {version}")
    tasks = registry.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError("task registry tasks must be a list")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(tasks):
        if not isinstance(raw, Mapping):
            raise ValueError(f"tasks[{index}] must be a mapping")
        task_id = str(raw.get("task_id") or "").strip().lower()
        if not _TASK_ID_RE.fullmatch(task_id):
            raise ValueError(
                f"tasks[{index}].task_id must use 1-64 lowercase letters, "
                "numbers, hyphens, or underscores"
            )
        if task_id in seen_ids:
            raise ValueError(f"duplicate task_id: {task_id}")
        seen_ids.add(task_id)

        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError(f"tasks[{index}].name must not be empty")
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"tasks[{index}].enabled must be a boolean")
        profile = raw.get("profile")
        if not isinstance(profile, Mapping):
            raise ValueError(f"tasks[{index}].profile must be a mapping")
        normalized.append(
            {
                "task_id": task_id,
                "name": name,
                "enabled": enabled,
                "profile": validate_profile(profile),
            }
        )
    return {"version": TASK_REGISTRY_VERSION, "tasks": normalized}


def create_monitor_task(
    registry: Mapping[str, Any] | None,
    name: str,
    profile: Mapping[str, Any],
    task_id: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Append one validated task and generate a stable ID when omitted."""
    data = validate_task_registry(registry)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("name must not be empty")
    existing = {task["task_id"] for task in data["tasks"]}
    candidate = str(task_id or "").strip().lower() or _task_id_from_name(clean_name)
    if task_id is None:
        base = candidate
        suffix = 2
        while candidate in existing:
            suffix_text = f"-{suffix}"
            candidate = f"{base[:64 - len(suffix_text)]}{suffix_text}"
            suffix += 1
    if not _TASK_ID_RE.fullmatch(candidate):
        raise ValueError(
            "task_id must use 1-64 lowercase letters, numbers, hyphens, or underscores"
        )
    if candidate in existing:
        raise ValueError(f"task_id already exists: {candidate}")
    data["tasks"].append(
        {
            "task_id": candidate,
            "name": clean_name,
            "enabled": enabled,
            "profile": validate_profile(profile),
        }
    )
    return data


def get_monitor_task(
    registry: Mapping[str, Any], task_id: str
) -> dict[str, Any]:
    data = validate_task_registry(registry)
    key = task_id.strip().lower()
    for task in data["tasks"]:
        if task["task_id"] == key:
            return deepcopy(task)
    raise KeyError(f"Unknown task_id: {task_id}")


def update_monitor_task(
    registry: Mapping[str, Any],
    task_id: str,
    profile_updates: Mapping[str, Any] | None = None,
    *,
    name: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Update only supplied task fields and preserve all other settings."""
    data = validate_task_registry(registry)
    key = task_id.strip().lower()
    for task in data["tasks"]:
        if task["task_id"] != key:
            continue
        if name is not None:
            clean_name = str(name).strip()
            if not clean_name:
                raise ValueError("name must not be empty")
            task["name"] = clean_name
        if enabled is not None:
            if not isinstance(enabled, bool):
                raise ValueError("enabled must be a boolean")
            task["enabled"] = enabled
        if profile_updates is not None:
            task["profile"] = merge_profile_update(task["profile"], profile_updates)
        return data
    raise KeyError(f"Unknown task_id: {task_id}")


def set_monitor_task_enabled(
    registry: Mapping[str, Any], task_id: str, enabled: bool
) -> dict[str, Any]:
    return update_monitor_task(registry, task_id, enabled=enabled)


def remove_monitor_task(
    registry: Mapping[str, Any], task_id: str
) -> dict[str, Any]:
    """Remove task configuration; per-task runtime state is handled separately."""
    data = validate_task_registry(registry)
    key = task_id.strip().lower()
    remaining = [task for task in data["tasks"] if task["task_id"] != key]
    if len(remaining) == len(data["tasks"]):
        raise KeyError(f"Unknown task_id: {task_id}")
    data["tasks"] = remaining
    return data


def remove_monitor_task_state(
    task_state: Mapping[str, Any], task_id: str
) -> dict[str, Any]:
    """Explicitly remove retained runtime state after a task was deleted."""
    data = deepcopy(dict(task_state))
    states = data.setdefault("task_states", {})
    states.pop(task_id.strip().lower(), None)
    return data


def _task_summary(task: Mapping[str, Any]) -> dict[str, Any]:
    profile = task["profile"]
    if profile["source_mode"] == "career_pages":
        sources: list[Any] = [
            {
                "company": page.get("company") or "Unknown company",
                "url": page["url"],
            }
            for page in profile["career_pages"]
        ]
    else:
        sources = [profile["search_url"]]
    return {
        "task_id": task["task_id"],
        "name": task["name"],
        "enabled": task["enabled"],
        "source_mode": profile["source_mode"],
        "sources": sources,
        "target_roles": list(profile["target_roles"]),
        "regions": list(profile["regions"]),
        "check_detailed_jd": profile["check_detailed_jd"],
        "jd_include_keywords": list(profile["jd_include_keywords"]),
        "jd_must_have_keywords": list(profile["jd_must_have_keywords"]),
        "jd_exclude_keywords": list(profile["jd_exclude_keywords"]),
    }


def list_monitor_tasks(
    registry: Mapping[str, Any] | None,
    include_disabled: bool = True,
) -> list[dict[str, Any]]:
    data = validate_task_registry(registry)
    return [
        _task_summary(task)
        for task in data["tasks"]
        if include_disabled or task["enabled"]
    ]


def group_monitor_tasks(
    registry: Mapping[str, Any] | None,
    include_disabled: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "linkedin": [],
        "career_pages": [],
    }
    for task in list_monitor_tasks(registry, include_disabled):
        grouped[task["source_mode"]].append(task)
    return grouped


def _format_task_rules(task: Mapping[str, Any], language: str) -> str:
    if not task["check_detailed_jd"]:
        return "关闭" if language == "zh" else "off"
    rules: list[str] = []
    labels = (
        ("jd_include_keywords", "任一包含" if language == "zh" else "include any"),
        ("jd_must_have_keywords", "必须词" if language == "zh" else "required"),
        ("jd_exclude_keywords", "排除词" if language == "zh" else "excluded"),
    )
    for field, label in labels:
        if task[field]:
            rules.append(f"{label}: {', '.join(task[field])}")
    return "; ".join(rules) or ("开启（无关键词硬筛选）" if language == "zh" else "on")


def format_monitor_task_overview(
    registry: Mapping[str, Any] | None,
    language: str = "zh",
) -> str:
    """Return a concise mode-separated view for conversational task queries."""
    if language not in {"zh", "en"}:
        raise ValueError("language must be 'zh' or 'en'")
    grouped = group_monitor_tasks(registry)
    total = sum(len(tasks) for tasks in grouped.values())
    enabled = sum(task["enabled"] for tasks in grouped.values() for task in tasks)
    if not total:
        return (
            "目前还没有已配置的监控任务。"
            if language == "zh"
            else "No monitor tasks are configured yet."
        )

    lines = [
        (
            f"已配置 {total} 个任务，其中 {enabled} 个已启用。"
            if language == "zh"
            else f"{total} tasks configured; {enabled} enabled."
        )
    ]
    headings = {
        "linkedin": "LinkedIn 搜索" if language == "zh" else "LinkedIn searches",
        "career_pages": "单独配置的 Career 页面" if language == "zh" else "Company career pages",
    }
    for mode in ("linkedin", "career_pages"):
        tasks = grouped[mode]
        lines.append(f"\n{headings[mode]}（{len(tasks)}）")
        if not tasks:
            lines.append("- 无" if language == "zh" else "- None")
            continue
        for task in tasks:
            status = (
                ("启用" if task["enabled"] else "停用")
                if language == "zh"
                else ("enabled" if task["enabled"] else "disabled")
            )
            if mode == "career_pages":
                source = ", ".join(item["company"] for item in task["sources"])
            else:
                source = task["sources"][0]
            lines.extend(
                [
                    f"- [{status}] {task['name']} (`{task['task_id']}`) — {source}",
                    (
                        f"  Title: {', '.join(task['target_roles'])}; "
                        f"地区: {', '.join(task['regions'])}; "
                        f"JD: {_format_task_rules(task, language)}"
                        if language == "zh"
                        else f"  Titles: {', '.join(task['target_roles'])}; "
                        f"regions: {', '.join(task['regions'])}; "
                        f"JD: {_format_task_rules(task, language)}"
                    ),
                ]
            )
    return "\n".join(lines)


def migrate_single_profile_to_registry(
    profile: Mapping[str, Any],
    dedupe_state: Mapping[str, Any] | None,
    name: str = "Default monitor",
    task_id: str = "default-monitor",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Wrap the legacy single profile/state without losing its dedupe history."""
    registry = create_monitor_task(None, name, profile, task_id=task_id)
    state = {
        "task_states": {task_id: deepcopy(dict(dedupe_state or {}))},
        "batch_history": [],
    }
    return registry, state


def run_monitor_tasks(
    registry: Mapping[str, Any],
    task_state: Mapping[str, Any] | None,
    sessions: Mapping[str, Any] | None = None,
    task_ids: list[str] | None = None,
    max_fetch_cards: int = 100,
    batch_history_limit: int = 30,
) -> tuple[str, dict[str, Any]]:
    """Run selected enabled tasks and retain independent state for each task."""
    if not isinstance(max_fetch_cards, int) or max_fetch_cards <= 0:
        raise ValueError("max_fetch_cards must be a positive integer")
    if not isinstance(batch_history_limit, int) or batch_history_limit <= 0:
        raise ValueError("batch_history_limit must be a positive integer")
    data = validate_task_registry(registry)
    state = deepcopy(dict(task_state or {}))
    states = state.setdefault("task_states", {})
    if not isinstance(states, dict):
        raise ValueError("task_state.task_states must be a mapping")
    session_map = dict(sessions or {})

    requested = None
    if task_ids is not None:
        if not isinstance(task_ids, list) or not all(
            isinstance(task_id, str) for task_id in task_ids
        ):
            raise ValueError("task_ids must be a list of strings")
        requested = [task_id.strip().lower() for task_id in task_ids]
        known = {task["task_id"] for task in data["tasks"]}
        unknown = sorted(set(requested) - known)
        if unknown:
            raise KeyError(f"Unknown task_id(s): {', '.join(unknown)}")
    selected = [
        task
        for task in data["tasks"]
        if requested is None or task["task_id"] in requested
    ]

    started_at = datetime.now(timezone.utc)
    started = perf_counter()
    sections: list[str] = []
    task_results: list[dict[str, Any]] = []
    totals = {
        "cards_collected": 0,
        "jobs_parsed": 0,
        "matched": 0,
        "rejected": 0,
        "notified": 0,
        "shown": 0,
    }
    attempted = 0
    succeeded = 0
    failed = 0
    skipped_disabled = 0

    for task in selected:
        task_id = task["task_id"]
        if not task["enabled"]:
            skipped_disabled += 1
            task_results.append(
                {
                    "task_id": task_id,
                    "name": task["name"],
                    "source_mode": task["profile"]["source_mode"],
                    "status": "skipped_disabled",
                }
            )
            continue
        attempted += 1
        try:
            digest, updated_task_state = run_monitor(
                task["profile"],
                deepcopy(states.get(task_id, {})),
                session=session_map.get(task_id),
                max_fetch_cards=max_fetch_cards,
            )
            states[task_id] = updated_task_state
            stats = updated_task_state.get("last_run_stats", {})
            for key in totals:
                totals[key] += int(stats.get(key, 0) or 0)
            succeeded += 1
            task_results.append(
                {
                    "task_id": task_id,
                    "name": task["name"],
                    "source_mode": task["profile"]["source_mode"],
                    "status": "succeeded",
                    "stats": stats,
                }
            )
            sections.append(
                f"## {task['name']} (`{task_id}`)\n\n{digest.strip()}"
            )
        except Exception as exc:
            failed += 1
            error = f"{type(exc).__name__}: {exc}"
            task_results.append(
                {
                    "task_id": task_id,
                    "name": task["name"],
                    "source_mode": task["profile"]["source_mode"],
                    "status": "failed",
                    "error": error,
                }
            )
            sections.append(
                f"## {task['name']} (`{task_id}`)\n\nTask failed: {error}"
            )

    batch_stats = {
        "started_at": started_at.isoformat(),
        "duration_ms": round((perf_counter() - started) * 1000, 3),
        "tasks_configured": len(data["tasks"]),
        "tasks_selected": len(selected),
        "tasks_attempted": attempted,
        "tasks_succeeded": succeeded,
        "tasks_failed": failed,
        "tasks_skipped_disabled": skipped_disabled,
        **totals,
        "task_results": task_results,
    }
    state["last_batch_stats"] = batch_stats
    history = state.setdefault("batch_history", [])
    if not isinstance(history, list):
        raise ValueError("task_state.batch_history must be a list")
    history.append(batch_stats)
    del history[:-batch_history_limit]

    header = (
        "# Job-monitor task batch\n\n"
        f"Selected {len(selected)}; attempted {attempted}; succeeded {succeeded}; "
        f"failed {failed}; disabled {skipped_disabled}; notified {totals['notified']}."
    )
    body = "\n\n".join(sections) if sections else "No enabled tasks were selected."
    return f"{header}\n\n{body}", state
