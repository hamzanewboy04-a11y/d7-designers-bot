# DEPLOY.md — Production / Railway Notes

## Bot service
Production bot runtime start command:

```bash
python main.py
```

Do **not** use the SQLite -> PostgreSQL importer as the permanent bot service start command.
The importer is a one-off operational tool and will not start Telegram polling.

## Importer
One-off command:

```bash
python scripts/sqlite_to_postgres_import.py \
  --sqlite-path /data/d7_bot_v2.sqlite3 \
  --database-url "$DATABASE_URL" \
  --truncate
```

Use it only for migration / recovery operations.

## Required Railway variables
Minimum bot runtime env:
- `BOT_TOKEN` or `TELEGRAM_BOT_TOKEN`
- `ADMIN_IDS`
- `DB_PATH`
- `REPORT_HOUR_UTC`

Optional:
- `DATABASE_URL`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`

## Current production reality
- Bot runtime still initializes `d7_bot.db.Database(config.db_path)`.
- Web app has partial PostgreSQL read support.
- PostgreSQL migration/import path exists, but production storage cutover is not fully complete.
- SQLite remains the effective primary runtime storage path for the bot unless code is further refactored.

## Recovery notes from 2026-03-30
Production deploy was restored after fixing:
1. importer module path resolution
2. SQLite -> PostgreSQL boolean coercion
3. SQLite -> PostgreSQL datetime coercion
4. Postgres `employees.telegram_id` widening to bigint
5. runtime column widening before import
6. Railway start command switched to `python main.py`

## Quick production smoke checklist
After deploy, verify:
- bot starts polling
- `/start` works
- `/register` works
- `/report` works for at least one real/controlled user
- admin command `/pendingpayments` works
- Google Sheets sync does not crash startup
- scheduled jobs register successfully

## Recommended future deploy model
- bot service: `python main.py`
- web service: `uvicorn web.app:app --host 0.0.0.0 --port $PORT`
- importer: one-off job only
