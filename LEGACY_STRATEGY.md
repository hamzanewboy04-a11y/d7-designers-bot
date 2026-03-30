# LEGACY_STRATEGY.md — Legacy Designer/Admin Layer Decision

## Executive summary
After reviewer + SMM bot cutover work, the remaining major legacy area is:
- designer registration/profile/runtime
- task submission flow (`/report` for designers)
- legacy payment callbacks for task-based reports
- legacy analytics/admin dashboards built on task tables

This area is still strongly tied to old SQLite-era tables and should be treated as a **legacy island** for now, not the next immediate migration target.

## What is already cut over or partially modernized
- PostgreSQL importer path exists
- web read paths now use PostgreSQL for current pages
- reviewer bot domain has PostgreSQL-backed runtime adapter
- SMM bot domain has PostgreSQL-backed runtime adapter

## What remains legacy-heavy

### Designer-facing runtime
Files:
- `d7_bot/handlers/report.py`
- `d7_bot/handlers/common.py`
- `d7_bot/handlers/register.py`

Key storage methods:
- `get_designer()`
- `upsert_designer()`
- `add_task()`
- `list_tasks_by_designer()`
- `get_designer_stats()`
- `list_admins()`

Why it is still legacy:
- uses `designers` table, not `employees`
- task model is separate from next-gen reviewer/SMM schema
- payment UX for task reports is tied to legacy callback flow
- Google Sheets exports are wired to this path

### Admin / analytics / payment layer
File:
- `d7_bot/handlers/admin.py`

Key storage methods:
- `list_tasks_by_date()`
- `list_missing_reports()`
- `get_employee_payment_history()`
- `get_paid_summary()`
- `get_pending_payments()`
- `get_pending_payments_summary()`
- `get_analytics_summary()`
- `get_geo_breakdown()`
- `get_geo_ranking()`
- `get_role_spend_breakdown()`
- `get_cost_per_day_breakdown()`
- `update_payment_status()`
- `get_report_summary()`
- `count_designers_by_role()`
- `get_employee_ranking()`

Why it is still legacy:
- metrics and payment summaries are built around task rows and old payment state fields
- tightly coupled to designer task report semantics
- duplicated dashboard/report builders depend on old aggregation shapes
- callback payment buttons directly mutate old task-payment state

## Decision
### Recommended near-term strategy
Treat the legacy designer/admin/task system as a **stabilized SQLite island**.

Meaning:
- keep it running on SQLite for now
- do not begin full migration until next-gen domains are considered stable in production
- do not mix partial task migration into PostgreSQL prematurely

## Why this is the right call now
1. Reviewer and SMM flows were already natural next-gen domains.
2. Legacy designer/admin layer has the highest coupling and broadest blast radius.
3. Migrating it now would touch:
   - registration identity
   - task ingestion
   - payments
   - analytics
   - dashboard
   - callbacks
   - sheets sync
4. That is effectively a final-phase rewrite, not a safe incremental cutover.

## Practical strategy

### Phase L0 — Freeze and document
- keep legacy task/admin/payment path on SQLite
- document that it is intentional
- avoid adding major new features to legacy task path

### Phase L1 — Isolate interfaces
Before any real migration, introduce service/adapters for:
- designer identity/profile
- task submission
- task payment workflow
- analytics/dashboard reads

Goal:
- reduce direct handler dependence on giant `d7_bot.db.Database`
- make future migration possible without rewriting handlers all at once

### Phase L2 — Decide product direction
A real migration should happen only if one of these is true:
1. legacy designer task flow is still core and long-lived
2. analytics/payment admin operations must join with next-gen domains in one DB
3. web admin needs full unified reporting across all domains

If not, legacy can remain isolated longer.

### Phase L3 — Final migration only when justified
If migration is chosen later, recommended order:
1. map `designers` -> `employees` identity reconciliation
2. create SQLAlchemy models for legacy task/payment tables
3. port analytics reads first
4. port payment callbacks second
5. port task ingestion last
6. decommission SQLite only after production parity checks

## Immediate recommendation
Do **not** migrate legacy designer/admin/task layer next.

Do this instead:
1. update docs/status to reflect split architecture clearly
2. add more regression coverage for reviewer/SMM domains
3. stabilize bot runtime with current mixed-mode architecture
4. only then decide whether legacy migration is worth the cost

## Bottom line
Reviewer + SMM are now the modernizing path.
Legacy designer/admin/task flow should remain a controlled, documented compatibility layer for now — not the next battlefield.
