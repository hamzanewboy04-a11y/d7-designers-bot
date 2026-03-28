# Storage groundwork

This package is a transition scaffold for moving from SQLite-only storage to a shared PostgreSQL-backed runtime.

Current state:
- runtime still uses `d7_bot.db.Database` (SQLite)
- config now supports `DATABASE_URL`
- storage backend selection metadata is centralized here

Next step:
- introduce SQLAlchemy async engine + models
- add repository layer
- add SQLite -> PostgreSQL importer
