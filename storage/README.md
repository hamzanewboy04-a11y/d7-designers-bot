# Storage groundwork

This package is a transition scaffold for moving from SQLite-only storage to a shared PostgreSQL-backed runtime.

Current state:
- runtime still uses `d7_bot.db.Database` (SQLite)
- config now supports `DATABASE_URL`
- storage backend selection metadata is centralized here
- Railway-style `postgres://` / `postgresql://` URLs are normalized to `postgresql+asyncpg://`

Next step:
- use Alembic against Railway Postgres
- add repository layer
- run SQLite -> PostgreSQL importer
