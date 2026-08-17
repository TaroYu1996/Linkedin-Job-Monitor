# First-Time Setup Conversation Template (CN + EN)

## 中文引导

### 开场：先检查已有任务

如果已有 task registry，先问：

> 你当前已有监控任务。需要我先按 `LinkedIn 搜索` 和 `单独配置的 Career 页面` 列出来，还是直接新增一个任务？

用户问“目前有哪些模式/配置/任务”时，先区分“Skill 支持的模式”和“用户已配置的任务”。问法不明确时，先说明支持 LinkedIn/Career 两种来源，再读取 registry 并分组展示；不要触发抓取。

### 新建任务：选择来源

你好，我可以帮你建立定期职位监控。请先选择一种模式：

1. **LinkedIn 搜索**：适合跨公司搜索，支持薪资、JD、seniority、公司黑白名单等完整筛选；需要可用的 LinkedIn 登录会话。
2. **指定公司 Career 页面**：适合持续刷新公司官网；内建支持 TD、CIBC、Scotiabank、BMO 和 RBC，默认只按目标职位和地区筛选。

请提供一个任务名称，并回复 `LinkedIn` 或 `公司 Career 页面`。

### 用户选择 LinkedIn

请提供：

- LinkedIn 搜索链接：
- 任务名称：
- 目标岗位（可多个）：
- 目标地区（可多个）：
- 办公模式（remote/hybrid/onsite，可多选）：

收到最小配置后，再询问用户是否需要薪资、详细 JD、关键词、seniority、公司黑白名单或其他高级条件。不要一次展示所有高级字段。

### 用户选择公司 Career 页面

请只提供：

- 公司名称和 Career 页面链接（可多个）：
- 任务名称：
- 想监控的职位名称或 title 关键词（可多个）：
- 目标地区（例如 Greater Toronto Area）：

可直接复制：

```text
- task_name: BMO Risk
- career_pages:
  - BMO: https://jobs.bmo.com/ca/en/search-results
- target_roles: risk analyst, risk manager, operational risk
- regions: greater toronto area
- jd_must_have_keywords: risk governance, controls
- jd_exclude_keywords: internship
```

默认配置：所有办公模式均可、先不抓详细 JD、不要求薪资、不启用 seniority 筛选。保留地区模糊匹配、Job ID 去重、职位状态、反馈学习和运行漏斗。

提示：可直接粘贴已带国家、工作类型或地区筛选的链接。Skill 会保留这些条件，但会用 `target_roles` 逐个刷新 title。BMO 的两种入口都支持；如同时配置，相同 Job ID 只会保留一份。

任务拆分规则：

- 同一银行的多个 title 共享相同 JD 规则时，放在一个任务。
- 不同银行使用不同 JD 规则时，每家银行建立独立任务。
- 同一银行的两组 title 也有不同必须词/排除词时，拆成两个任务。

只在用户主动需要时再问：

- 是否抓详细 JD，用于薪资或 JD 关键词检查？
- 每天刷新几次？
- 是否限制 remote/hybrid/onsite？

### 保存确认

总结任务 ID、来源模式、页面或搜索链接、所有目标 title、地区、JD 规则和刷新频率；校验并保存 registry。只有实际完成一次公开页面读取或认证 LinkedIn 读取后，才报告首次运行成功。

## English guide

### Opening: choose a source

If tasks already exist, first offer a grouped overview without running them. Otherwise, ask for a task name and choose one source:

1. **LinkedIn search** for broader multi-company search and advanced salary, JD, seniority, and company filters; this requires an authenticated LinkedIn session.
2. **Specific company career pages** for lightweight monitoring of employer sites, with built-in TD, CIBC, Scotiabank, BMO, and RBC support; this defaults to title and region matching only.

Reply with `LinkedIn` or `company career pages`.

### LinkedIn minimum fields

- LinkedIn search URL
- Target roles
- Regions
- Allowed work modes

Offer advanced filters only after the minimum profile is collected.

### Career-page minimum fields

- Company names and public career-page URLs
- Task name
- Target titles or role phrases
- Regions

Default to all work modes and `check_detailed_jd=false`. Keep fuzzy region matching, source-scoped Job ID dedupe, lifecycle state, feedback learning, and funnel statistics. Ask about JD checks, refresh frequency, or work-mode restrictions only when useful.

Keep multiple titles in one task when they share JD rules. Create separate bank or title-group tasks when their must-have or exclude rules differ.
