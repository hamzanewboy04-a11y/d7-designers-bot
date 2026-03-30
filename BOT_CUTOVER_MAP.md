# BOT_CUTOVER_MAP.md — Bot Storage Cutover Map

## Goal
Map next-gen Telegram bot handlers to current storage paths and identify the safest first PostgreSQL cutover slice.

## Current reality
Bot runtime (`d7_bot/bot.py`) still injects a SQLite-backed `Database(config.db_path)` into handlers.
That means all bot commands currently execute against the SQLite-oriented `d7_bot.db.Database` layer, even when PostgreSQL exists.

## Handler map

### 1. Reviewer v2 flow
File: `d7_bot/handlers/reviewer_v2.py`

Current DB methods used:
- `get_employee_by_telegram_id()`
- `list_review_rate_rules()`
- `create_review_entry_v2()`
- `get_review_entry_summary()`
- `is_admin()`

Domain type:
- next-gen domain model
- good cutover candidate

Risk level:
- medium

Reason:
- mostly self-contained next-gen flow
- depends on employee lookup + review entry writes + rate rules
- does not depend on legacy designer task rows

### 2. PM reviewer moderation flow
File: `d7_bot/handlers/pm.py`

Current DB methods used:
- `get_employee_by_telegram_id()`
- `list_pending_review_entries()`
- `verify_review_entry()`
- `reject_review_entry()`
- `create_reviewer_payout_batches()`
- `list_pending_reviewer_batches()`
- `mark_reviewer_batch_paid()`
- `list_recent_reviewer_batches()`
- `get_employee()`
- `is_admin()`

Domain type:
- next-gen domain model
- very strong cutover candidate

Risk level:
- medium

Reason:
- strongly coupled to reviewer v2 data already stored in next-gen tables
- operationally important
- a natural extension after reviewer v2 submission path

### 3. PM SMM flow
File: `d7_bot/handlers/pm.py`

Current DB methods used:
- `get_employee_by_telegram_id()`
- `list_employees_by_role()`
- `get_employee()`
- `add_smm_assignment()`
- `list_active_smm_assignments_detailed()`
- `list_active_smm_assignments()`
- `add_smm_daily_entry_v2()`
- `get_smm_weekly_summary()`
- `get_smm_weekly_details()`
- `create_smm_weekly_batches()`
- `list_pending_smm_batches()`
- `mark_smm_batch_paid()`
- `list_recent_smm_batches()`
- `is_admin()`

Domain type:
- next-gen domain model
- strong cutover candidate

Risk level:
- medium-high

Reason:
- larger command surface than reviewer flow
- includes creation + preview + batching + paid notifications
- still isolated from legacy designer task domain, which is good

### 4. Legacy designer/report flow
File: `d7_bot/handlers/report.py`

Current DB methods used for designer tasks:
- `get_designer()`
- `add_task()`
- `list_admins()`
- `is_admin()`
- plus legacy reviewer fallback path via `add_reviewer_entry()`

Domain type:
- legacy / hybrid path

Risk level:
- high

Reason:
- tightly coupled to legacy `designers` / `reports` tables
- also tied to Google Sheets export and admin payment buttons
- should not be first cutover slice

## Best first cutover slice
Safest first PostgreSQL bot cutover:

### Slice A — reviewer v2 + PM reviewer flows
Why this slice first:
- it already lives in next-gen tables
- fewer legacy dependencies
- business boundary is clear
- web already reads reviewer data from PostgreSQL
- successful cutover would create end-to-end consistency for reviewer operations

Required capabilities to implement:
1. employee lookup by telegram id
2. review rate rules read
3. review entry create + summary read
4. reviewer moderation queue read
5. verify/reject write ops
6. payout batch create/list/mark paid/history
7. employee lookup for notifications
8. admin check strategy (temporary SQLite fallback or separate admin store strategy)

## Proposed implementation order

### Phase A1
Introduce PostgreSQL repositories/services for reviewer write/read flows:
- reviewer self-submission
- reviewer queue
- verify/reject
- batch create/list/paid/history

### Phase A2
Wire only reviewer handlers to new backend adapter while leaving bot runtime otherwise unchanged.
Possible adapter patterns:
- repository bundle injected into dispatcher workflow data
- facade object matching methods currently expected by handlers
- dedicated `ReviewerDomainService`

### Phase A3
After reviewer cutover is stable, repeat for SMM flow.

## Important open design choices
1. How to handle `is_admin()` during partial cutover?
   - keep using SQLite-backed admin list temporarily
   - or move admin identity into PostgreSQL too
2. How to reconcile employee/admin/designer identity during mixed-mode runtime?
3. Whether to introduce one big bot repository facade or smaller domain services first?

## Recommendation
Next implementation target should be:
**PostgreSQL-backed reviewer domain service for bot handlers (`reviewer_v2.py` + reviewer-related PM commands).**
