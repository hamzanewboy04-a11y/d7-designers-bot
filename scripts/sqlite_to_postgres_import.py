from __future__ import annotations

import argparse
import asyncio
import sqlite3
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TABLES = [
    "designers",
    "admins",
    "reports",
    "employees",
    "review_rate_rules",
    "review_entries",
    "review_entry_items",
    "smm_assignments",
    "smm_daily_entries",
    "payment_batches",
    "payment_batch_items",
]


def fetch_rows(sqlite_path: str, table: str) -> tuple[list[str], list[tuple]]:
    conn = sqlite3.connect(sqlite_path)
    try:
        cur = conn.execute(f"SELECT * FROM {table}")
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        return columns, rows
    finally:
        conn.close()


def sqlite_count(sqlite_path: str, table: str) -> int:
    conn = sqlite3.connect(sqlite_path)
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        return int(cur.fetchone()[0])
    finally:
        conn.close()


async def truncate_tables(conn, tables: Iterable[str]) -> None:
    for table in reversed(list(tables)):
        await conn.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))


async def import_table(conn, sqlite_path: str, table: str) -> int:
    columns, rows = fetch_rows(sqlite_path, table)
    if not rows:
        return 0

    quoted_columns = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    stmt = text(f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})')

    payload = [dict(zip(columns, row)) for row in rows]
    await conn.execute(stmt, payload)
    return len(rows)


async def postgres_count(conn, table: str) -> int:
    result = await conn.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
    return int(result.scalar_one())


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import SQLite data into PostgreSQL")
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--truncate", action="store_true")
    args = parser.parse_args()

    engine = create_async_engine(args.database_url, future=True)
    async with engine.begin() as conn:
        if args.truncate:
            await truncate_tables(conn, TABLES)

        for table in TABLES:
            imported = await import_table(conn, args.sqlite_path, table)
            print(f"imported {table}: {imported}")

        print("--- row count validation ---")
        for table in TABLES:
            sqlite_rows = sqlite_count(args.sqlite_path, table)
            pg_rows = await postgres_count(conn, table)
            print(f"{table}: sqlite={sqlite_rows} postgres={pg_rows}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
