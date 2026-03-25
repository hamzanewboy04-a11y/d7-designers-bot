from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class Designer:
    telegram_id: int
    username: str | None
    d7_nick: str
    formats: list[str]
    wallet: str


@dataclass
class TaskEntry:
    designer_id: int
    report_date: str
    task_code: str
    cost_usdt: float


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    async def migrate(self) -> None:
        """
        Safe migration: if the old schema (with experience/portfolio columns)
        exists, recreate the table without them.
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("PRAGMA table_info(designers)")
            columns = {row[1] for row in await cursor.fetchall()}

            if "experience" in columns or "portfolio_json" in columns:
                logger.info("Migrating designers table: removing experience/portfolio columns")
                await db.executescript("""
                    CREATE TABLE IF NOT EXISTS designers_new (
                        telegram_id INTEGER PRIMARY KEY,
                        username TEXT,
                        d7_nick TEXT NOT NULL,
                        formats_json TEXT NOT NULL,
                        wallet TEXT NOT NULL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );

                    INSERT INTO designers_new
                        (telegram_id, username, d7_nick, formats_json, wallet, created_at, updated_at)
                    SELECT
                        telegram_id,
                        username,
                        d7_nick,
                        formats_json,
                        wallet,
                        COALESCE(created_at, CURRENT_TIMESTAMP),
                        COALESCE(updated_at, CURRENT_TIMESTAMP)
                    FROM designers;

                    DROP TABLE designers;

                    ALTER TABLE designers_new RENAME TO designers;
                """)
                await db.commit()
                logger.info("Migration complete.")

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS designers (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    d7_nick TEXT NOT NULL,
                    formats_json TEXT NOT NULL,
                    wallet TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS admins (
                    telegram_id INTEGER PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    designer_id INTEGER NOT NULL,
                    report_date TEXT NOT NULL,
                    task_code TEXT NOT NULL,
                    cost_usdt REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (designer_id) REFERENCES designers(telegram_id) ON DELETE CASCADE,
                    UNIQUE(designer_id, report_date, task_code)
                );

                CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date);
                CREATE INDEX IF NOT EXISTS idx_reports_designer ON reports(designer_id);
            """)
            await db.commit()

        # Run migration after table creation (in case of old schema)
        await self.migrate()

    # ── Designers ──────────────────────────────────────────────────────────

    async def upsert_designer(self, designer: Designer) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO designers
                    (telegram_id, username, d7_nick, formats_json, wallet, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username      = excluded.username,
                    d7_nick       = excluded.d7_nick,
                    formats_json  = excluded.formats_json,
                    wallet        = excluded.wallet,
                    updated_at    = CURRENT_TIMESTAMP
                """,
                (
                    designer.telegram_id,
                    designer.username,
                    designer.d7_nick,
                    json.dumps(designer.formats, ensure_ascii=False),
                    designer.wallet,
                ),
            )
            await db.commit()

    async def get_designer(self, telegram_id: int) -> Designer | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT telegram_id, username, d7_nick, formats_json, wallet
                FROM designers WHERE telegram_id = ?
                """,
                (telegram_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return _row_to_designer(row)

    async def list_designers(self) -> list[Designer]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT telegram_id, username, d7_nick, formats_json, wallet
                FROM designers ORDER BY d7_nick
                """
            )
            rows = await cursor.fetchall()
            return [_row_to_designer(r) for r in rows]

    # ── Admins ─────────────────────────────────────────────────────────────

    async def add_admin(self, telegram_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO admins (telegram_id) VALUES (?)", (telegram_id,)
            )
            await db.commit()

    async def list_admins(self) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT telegram_id FROM admins")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def is_admin(self, telegram_id: int, config_admin_ids: list[int]) -> bool:
        """Return True if user is in config admins OR db admins."""
        if telegram_id in config_admin_ids:
            return True
        db_admins = await self.list_admins()
        return telegram_id in db_admins

    # ── Reports / Tasks ────────────────────────────────────────────────────

    async def task_exists(
        self, designer_id: int, report_date: str, task_code: str
    ) -> bool:
        """Check whether the same task was already submitted for this date."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT 1 FROM reports
                WHERE designer_id = ? AND report_date = ? AND task_code = ?
                LIMIT 1
                """,
                (designer_id, report_date, task_code),
            )
            return await cursor.fetchone() is not None

    async def add_task(self, task: TaskEntry) -> bool:
        """
        Insert a task entry.
        Returns True on success, False if a duplicate exists.
        """
        if await self.task_exists(task.designer_id, task.report_date, task.task_code):
            return False
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO reports (designer_id, report_date, task_code, cost_usdt)
                VALUES (?, ?, ?, ?)
                """,
                (task.designer_id, task.report_date, task.task_code, task.cost_usdt),
            )
            await db.commit()
        return True

    async def list_tasks_by_date(self, report_date: date) -> list[tuple]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT d.d7_nick, d.wallet, r.task_code, r.cost_usdt
                FROM reports r
                JOIN designers d ON d.telegram_id = r.designer_id
                WHERE r.report_date = ?
                ORDER BY d.d7_nick, r.task_code
                """,
                (report_date.isoformat(),),
            )
            return await cursor.fetchall()

    async def list_tasks_by_designer(
        self, designer_id: int, days: int = 7
    ) -> list[tuple]:
        """
        Return tasks for *designer_id* over the last *days* days (inclusive today).
        Each row: (report_date, task_code, cost_usdt)
        """
        since = (datetime.utcnow().date() - timedelta(days=days - 1)).isoformat()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT report_date, task_code, cost_usdt
                FROM reports
                WHERE designer_id = ? AND report_date >= ?
                ORDER BY report_date DESC, task_code
                """,
                (designer_id, since),
            )
            return await cursor.fetchall()

    async def get_designer_stats(self, designer_id: int, days: int = 7) -> dict:
        """
        Return statistics for a designer over the last *days* days.
        Returns {"task_count": int, "total_usdt": float}
        """
        since = (datetime.utcnow().date() - timedelta(days=days - 1)).isoformat()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(cost_usdt), 0.0)
                FROM reports
                WHERE designer_id = ? AND report_date >= ?
                """,
                (designer_id, since),
            )
            row = await cursor.fetchone()
            if not row:
                return {"task_count": 0, "total_usdt": 0.0}
            return {"task_count": int(row[0]), "total_usdt": float(row[1])}


# ── helpers ────────────────────────────────────────────────────────────────


def _row_to_designer(row: tuple) -> Designer:
    return Designer(
        telegram_id=row[0],
        username=row[1],
        d7_nick=row[2],
        formats=json.loads(row[3]),
        wallet=row[4],
    )
