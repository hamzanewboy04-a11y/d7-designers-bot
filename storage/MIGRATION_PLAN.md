# PostgreSQL Migration Scaffold

## Current state
- Runtime still uses SQLite via `d7_bot.db.Database`
- `DATABASE_URL` support exists in config
- SQLAlchemy/Alembic skeleton exists in `storage/` + `alembic/`

## Next implementation steps
1. Add dependencies: sqlalchemy, asyncpg, alembic
2. Create a one-off importer from SQLite -> PostgreSQL
3. Validate row counts across all key tables
4. Switch bot service to `DATABASE_URL`
5. Switch web service to `DATABASE_URL`
6. Gradually replace direct SQLite layer with repositories/services

## Importer
One-off script:
```bash
python scripts/sqlite_to_postgres_import.py \
  --sqlite-path /data/d7_bot_v2.sqlite3 \
  --database-url "$DATABASE_URL" \
  --truncate
```

Current scope:
- imports next-gen domain tables only
- excludes legacy SQLite tables (`designers`, `admins`, `reports`)
- aligns source columns to current Postgres schema automatically

Expected use:
- run after Alembic schema migration
- verify printed row counts
- then switch web read paths to `DATABASE_URL`
