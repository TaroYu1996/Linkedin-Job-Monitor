# First-Time Setup Conversation Template (CN + EN)

Use this template when a user has no saved profile and wants to set up `linkedin-job-monitor` for the first time.

---

## 中文版（首次配置）

### 目标
在一轮或多轮对话中，收集最小必填字段并确认可选偏好，最后得到可验证的 profile。

### 机器人开场
你好！我可以先帮你完成 **LinkedIn 职位监控** 的首次配置。  
我会先收集 4 个必填项，然后再补充可选筛选条件，最后你就可以直接跑监控。

必填项是：
1. LinkedIn 搜索链接（search_url）
2. 目标岗位（target_roles）
3. 目标地区（regions）
4. 办公模式（allowed_location_types：remote/hybrid/onsite）

---

### 第 1 步：收集必填字段

请你直接按下面格式回复（可以复制后填写）：

- search_url:
- target_roles: （可多个，用逗号分隔）
- regions: （可多个，用逗号分隔）
- allowed_location_types: （remote/hybrid/onsite，可多选）

---

### 第 2 步：收集可选字段（可跳过）

为了让结果更精准，你还可以补充这些项（没有就写“跳过”）：

- minimum_salary_cad:
- salary_required: （true/false）
- salary_hours_per_week: （默认 40）
- salary_weeks_per_year: （默认 52）
- region_aliases: （可选，自定义地区及其城市/别名）
- region_fuzzy_threshold: （默认 0.86）
- unknown_region_policy: （reject/include）
- check_detailed_jd: （是否检查详细 JD，true/false；默认 true）
- output_mode: （仅完全符合：matches_only；包含部分符合：include_partial_matches）
- seniority:
- title_include_keywords:
- title_exclude_keywords:
- jd_include_keywords:
- jd_must_have_keywords:
- jd_exclude_keywords:
- company_blacklist:
- company_whitelist:
- max_results_per_digest:
- dedupe_window_days:
- expire_after_missing_runs:
- run_history_limit:
- feedback_learning_enabled: （true/false）
- feedback_score_weight: （0–5，默认 1）
- runs_per_day:

---

### 第 3 步：确认与保存

收到，我会：
1. 规范化并校验配置
2. 保存 profile
3. 用该 profile 运行一次监控并返回简要 digest

是否现在开始首次运行？（是/否）

---

### 中文示例对话

**用户**：我要配置职位监控。  
**机器人**：好的，我们先收集 4 个必填项……（发送第 1 步模板）  
**用户**：
- search_url: https://www.linkedin.com/jobs/search/?keywords=data%20analyst&location=Canada
- target_roles: data analyst, business analyst
- regions: canada, ontario
- allowed_location_types: remote, hybrid

**机器人**：收到。要不要补充可选筛选（薪资、关键词、公司黑白名单等）？  
**用户**：
- minimum_salary_cad: 85000
- salary_required: false
- title_include_keywords: analytics, sql
- jd_include_keywords: dashboard, experimentation
- max_results_per_digest: 10
- dedupe_window_days: 14
- runs_per_day: 2
其余跳过。

**机器人**：已完成配置并保存。是否现在运行一次并返回简要摘要？

---

## English Version (First-Time Setup)

### Goal
Collect required profile fields first, then optional preferences, validate the profile, save it, and run the first monitor pass.

### Assistant Opening
Great — I can help you set up **LinkedIn Job Monitor** for first-time use.  
I’ll collect 4 required fields first, then optional filters, and finally run your first digest.

Required fields:
1. LinkedIn search URL (`search_url`)
2. Target role families (`target_roles`)
3. Regions (`regions`)
4. Allowed work modes (`allowed_location_types`: remote/hybrid/onsite)

---

### Step 1: Collect Required Fields

Please reply using this format:

- search_url:
- target_roles: (comma-separated)
- regions: (comma-separated)
- allowed_location_types: (remote/hybrid/onsite, multi-select)

---

### Step 2: Collect Optional Fields (Skip if not needed)

For better precision, you can optionally provide:

- minimum_salary_cad:
- salary_required: (true/false)
- salary_hours_per_week: (default 40)
- salary_weeks_per_year: (default 52)
- region_aliases: (optional region-to-city/alias mapping)
- region_fuzzy_threshold: (default 0.86)
- unknown_region_policy: (`reject` or `include`)
- check_detailed_jd: (inspect detailed JD text; true/false, default true)
- output_mode: (`matches_only` or `include_partial_matches`)
- seniority:
- title_include_keywords:
- title_exclude_keywords:
- jd_include_keywords:
- jd_must_have_keywords:
- jd_exclude_keywords:
- company_blacklist:
- company_whitelist:
- max_results_per_digest:
- dedupe_window_days:
- expire_after_missing_runs:
- run_history_limit:
- feedback_learning_enabled: (true/false)
- feedback_score_weight: (0–5, default 1)
- runs_per_day:

---

### Step 3: Confirm and Save

Thanks — I will now:
1. Normalize and validate your profile
2. Save the profile
3. Run one monitor cycle and return a brief digest

Start first run now? (yes/no)

---

### English Example Conversation

**User**: I want to set up job monitoring.  
**Assistant**: Great — let’s collect 4 required fields first… (send Step 1 template)  
**User**:
- search_url: https://www.linkedin.com/jobs/search/?keywords=data%20analyst&location=Canada
- target_roles: data analyst, business analyst
- regions: canada, ontario
- allowed_location_types: remote, hybrid

**Assistant**: Got it. Do you want to add optional filters (salary, keywords, company lists, etc.)?  
**User**:
- minimum_salary_cad: 85000
- salary_required: false
- title_include_keywords: analytics, sql
- jd_include_keywords: dashboard, experimentation
- max_results_per_digest: 10
- dedupe_window_days: 14
- runs_per_day: 2
skip the rest.

**Assistant**: Setup is saved. Do you want me to run the monitor now and return a brief digest?
