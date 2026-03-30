# PLAN.md — D7 Designers Bot Completion Plan

## Current reality
Project is in a transition state between:
- legacy SQLite bot runtime (`d7_bot/db.py`)
- next-gen PostgreSQL scaffold (`storage/`, Alembic, importer)
- partial service layer
- partial web admin MVP

Production was restored on 2026-03-30 by fixing:
- importer project-root import path
- SQLite -> Postgres boolean coercion
- SQLite -> Postgres datetime coercion
- Postgres `employees.telegram_id` widening to bigint
- runtime schema widening in importer for existing Postgres schema
- Railway bot start command (`python main.py` instead of importer-only command)

## Priority roadmap

### P0 — Production stabilization
1. Lock Railway runtime conventions
   - Bot service start command: `python main.py`
   - Importer is one-off only, not permanent runtime
   - Document required Railway variables
2. Run production smoke checks
   - `/start`
   - `/register`
   - `/report`
   - `/adminreport`
   - `/pendingpayments`
   - reviewer v2 basic flow
   - SMM basic flow
3. Write deployment notes and rollback notes

### P1 — Unified storage backend
Goal: bot + web must use one shared source of truth in production.

1. Decide production source of truth: PostgreSQL
2. Audit all bot read/write paths that still use SQLite-only `Database`
3. Introduce repository/service abstractions for next-gen domain runtime paths
4. Switch bot next-gen flows to PostgreSQL-backed repositories/services
5. Decide strategy for legacy tables:
   - temporary SQLite fallback
   - or migrate legacy tables too
6. Remove production dependency on SQLite as primary storage

### P2 — Reduce architecture debt
1. Split oversized `d7_bot/db.py`
2. Move business logic out of handlers into services
3. Keep repositories focused on persistence only
4. Make role/domain boundaries explicit:
   - designers
   - reviewer
   - smm
   - payouts
   - admin analytics

### P3 — Web admin completion
1. Dashboard stability
2. Employees page
3. Reviewer queue page
4. Payouts page
5. SMM assignments page
6. Add simple auth/protection

### P4 — Tests and docs
1. Installable local test flow (`.venv`, requirements, unittest/pytest strategy)
2. Expand edge-case tests
3. Add integration smoke tests for critical command flows
4. Sync README with real architecture
5. Add OPERATIONS.md / DEPLOY.md

## Immediate next execution order
1. Create deployment/operations notes
2. Audit SQLite-vs-Postgres runtime usage
3. Produce a storage cutover design
4. Implement first safe Postgres-backed bot path
5. Add tests for that path

## Guardrails
- Do not run importer on every service start in production.
- Do not add major features before storage cutover is clarified.
- Prefer small, reversible migrations.
- Keep bot operational while refactoring.
