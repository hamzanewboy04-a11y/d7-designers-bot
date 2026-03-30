# STORAGE_AUDIT.md — SQLite vs PostgreSQL Runtime Audit

## Summary
The project is currently split between:
- SQLite runtime access through `d7_bot.db.Database`
- partial PostgreSQL support through `storage/` + SQLAlchemy + Alembic + importer

The main unfinished architecture task is to complete storage cutover so bot + web share one source of truth.

## Current runtime usage map

### Bot runtime
`d7_bot/bot.py`
- creates `Database(config.db_path)`
- calls `await db.init()`
- all bot handlers are therefore wired to the SQLite-backed `Database` class

### Web runtime
`web/app.py`
- always creates `Database(config.db_path)`
- if `DATABASE_URL` exists, also creates SQLAlchemy session factory
- uses PostgreSQL repositories only for some read paths:
  - `PostgresDashboardReadRepository`
  - `PostgresEmployeeReadRepository`
- still uses SQLite-backed services for reviewer/smm pages

### Services still coupled to SQLite Database
- `services/reviewer.py`
- `services/smm.py`
- most of `services/payroll.py` via SQLite-oriented service composition

## What is already PostgreSQL-aware
- `storage/session.py`
- `storage/models.py`
- Alembic scaffold
- importer script
- `storage.repositories.employees`
- `storage.repositories.dashboard`
- part of web read flow

## Main risk
Bot and web can diverge in storage backend:
- web may read PostgreSQL
- bot still writes SQLite

That creates inconsistent operator visibility and future data drift.

## Recommended cutover sequence

### Phase 1 — next-gen read parity
1. Add PostgreSQL repositories for:
   - reviewer pending queue
n   - reviewer pending batches
   - smm assignments list
   - smm pending batches
2. Update services to accept either repository-style objects or SQLite Database
3. Make web runtime fully use PostgreSQL when `DATABASE_URL` is present

### Phase 2 — bot next-gen write cutover
1. Identify bot commands for next-gen domains:
   - reviewer v2
   - pm review verify/reject
   - reviewer payout batch ops
   - smm assignment/daily/batch ops
2. Introduce repository/service write interfaces for these flows
3. Switch these handlers off direct SQLite-only methods

### Phase 3 — legacy strategy decision
Decide one of:
- keep legacy designer/admin/report flow on SQLite temporarily
- or migrate legacy tables and switch all runtime access to PostgreSQL

### Phase 4 — simplify runtime
- reduce `d7_bot/db.py`
- remove production dependence on SQLite as primary DB
- keep importer as historical migration tool only

## Immediate actionable next task
Implement PostgreSQL repositories for reviewer + smm read paths so the entire web admin can consistently read from PostgreSQL.
