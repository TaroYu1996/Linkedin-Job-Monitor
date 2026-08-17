# Monitor Task Management

Use a task registry when the user has more than one independent search, bank, title group, or JD rule set. Keep the legacy single-profile path available for simple setups.

## Registry shape

```yaml
version: 1
tasks:
  - task_id: linkedin-marketing
    name: LinkedIn marketing
    enabled: true
    profile:
      source_mode: linkedin
      search_url: https://www.linkedin.com/jobs/search/?keywords=marketing
      target_roles: [marketing analyst, marketing manager]
      regions: [greater toronto area]
      allowed_location_types: [remote, hybrid]
  - task_id: bmo-risk
    name: BMO risk
    enabled: true
    profile:
      source_mode: career_pages
      career_pages:
        - company: BMO
          url: https://jobs.bmo.com/ca/en/search-results
      target_roles: [risk analyst, risk manager]
      regions: [greater toronto area]
      jd_must_have_keywords: [risk governance]
```

Each task owns a normal validated profile. This gives every bank or LinkedIn search independent titles, regions, salary/JD rules, run statistics, dedupe records, lifecycle state, and feedback learning.

## Conversational operations

When the user asks “目前有哪些模式/任务/配置”:

1. Distinguish capability from saved state: “支持哪些模式” means explain the two source modes; “我已经配置了哪些” means inspect the registry. If ambiguous, give the two-mode sentence and then the saved-task overview.
2. Load the saved task registry.
3. Call `format_monitor_task_overview(registry, language="zh")`.
4. Show `LinkedIn 搜索` separately from `单独配置的 Career 页面`.
5. Include enabled/disabled state, task ID, source/company, all target titles, regions, and concise JD rules. Do not start a refresh unless requested.

For create/update actions:

- Ask for task name, source mode, source URL/page, one or more target titles, regions, and only the JD/salary rules the user wants.
- Put several title keywords in one task when they share the same filter rules.
- Create separate tasks for the same bank when different titles need different JD must-have/exclude rules.
- Use `create_monitor_task`, `update_monitor_task`, or `set_monitor_task_enabled`; preserve unspecified settings.
- Newly supplied JD keyword rules automatically enable detailed-JD checks unless the user explicitly disables them.
- Confirm the exact task ID before `remove_monitor_task`. Retained runtime history is removed separately with `remove_monitor_task_state` only when explicitly requested.

For refresh actions:

- “刷新全部” means all enabled tasks.
- “刷新 TD 和 BMO” means resolve the named tasks and pass their IDs to `run_monitor_tasks(..., task_ids=[...])`.
- Disabled tasks remain skipped until enabled, including when explicitly selected.
- Provide a session adapter keyed by task ID for every selected LinkedIn task. Built-in supported Career tasks need no session.
- Persist the returned task state. It keeps `task_states` isolated by ID plus aggregate `last_batch_stats` and bounded `batch_history`.
- Report per-task failures without discarding successful task results or prior state.

## Legacy migration

Use `migrate_single_profile_to_registry(profile, dedupe_state, name, task_id)` once to wrap an existing single profile and preserve its state. Do not silently duplicate the old profile into multiple tasks.
