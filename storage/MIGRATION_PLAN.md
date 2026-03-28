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
