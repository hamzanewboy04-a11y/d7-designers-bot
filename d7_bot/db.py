from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class Designer:
    telegram_id: int
    username: str | None
    d7_nick: str
    role: str
    wallet: str


@dataclass
class TaskEntry:
    designer_id: int
    report_date: str
    task_code: str
    cost_usdt: float
    task_prefix: str = ""
    task_group: str = ""
    task_geo: str = ""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    async def migrate(self) -> None:
        """
        Safe migration: handles schema changes for designers and reports tables.
        """
        async with aiosqlite.connect(self.path) as db:
            # --- designers: add role column if absent ---
            cursor = await db.execute("PRAGMA table_info(designers)")
            columns = {row[1] for row in await cursor.fetchall()}

            if "experience" in columns or "portfolio_json" in columns:
                logger.info("Migrating designers table: removing experience/portfolio columns")
                await db.executescript("""
                    CREATE TABLE IF NOT EXISTS designers_new (
                        telegram_id INTEGER PRIMARY KEY,
                        username TEXT,
                        d7_nick TEXT NOT NULL,
                        formats_json TEXT NOT NULL DEFAULT '[]',
                        role TEXT NOT NULL DEFAULT '',
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
                        COALESCE(formats_json, '[]'),
                        wallet,
                        COALESCE(created_at, CURRENT_TIMESTAMP),
                        COALESCE(updated_at, CURRENT_TIMESTAMP)
                    FROM designers;

                    DROP TABLE designers;

                    ALTER TABLE designers_new RENAME TO designers;
                """)
                await db.commit()
                logger.info("Designers migration complete.")
                # refresh columns
                cursor = await db.execute("PRAGMA table_info(designers)")
                columns = {row[1] for row in await cursor.fetchall()}

            if "role" not in columns:
                logger.info("Migrating designers table: adding role column")
                await db.execute(
                    "ALTER TABLE designers ADD COLUMN role TEXT NOT NULL DEFAULT ''"
                )
                await db.commit()
                logger.info("Designers role migration complete.")

            # --- reports migration: add payment columns if absent ---
            cursor = await db.execute("PRAGMA table_info(reports)")
            report_cols = {row[1] for row in await cursor.fetchall()}

            if report_cols and "payment_status" not in report_cols:
                logger.info("Migrating reports table: adding payment columns")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN payment_status TEXT DEFAULT 'pending'"
                )
                await db.execute("ALTER TABLE reports ADD COLUMN paid_at TEXT")
                await db.execute("ALTER TABLE reports ADD COLUMN paid_by INTEGER")
                await db.commit()
                logger.info("Reports payment migration complete.")

            if report_cols and "payment_comment" not in report_cols:
                logger.info("Migrating reports table: adding payment_comment column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN payment_comment TEXT DEFAULT ''"
                )
                await db.commit()
                logger.info("Reports payment_comment migration complete.")

            # v7: add task_prefix, task_group, task_geo
            cursor = await db.execute("PRAGMA table_info(reports)")
            report_cols = {row[1] for row in await cursor.fetchall()}

            if report_cols and "task_prefix" not in report_cols:
                logger.info("Migrating reports table: adding task_prefix column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN task_prefix TEXT NOT NULL DEFAULT ''"
                )
                await db.commit()

            if report_cols and "task_group" not in report_cols:
                logger.info("Migrating reports table: adding task_group column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN task_group TEXT NOT NULL DEFAULT ''"
                )
                await db.commit()

            if report_cols and "task_geo" not in report_cols:
                logger.info("Migrating reports table: adding task_geo column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN task_geo TEXT NOT NULL DEFAULT ''"
                )
                await db.commit()
                logger.info("Reports v7 task fields migration complete.")

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS designers (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    d7_nick TEXT NOT NULL,
                    formats_json TEXT NOT NULL DEFAULT '[]',
                    role TEXT NOT NULL DEFAULT '',
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
                    payment_status TEXT DEFAULT 'pending',
                    paid_at TEXT,
                    paid_by INTEGER,
                    payment_comment TEXT DEFAULT '',
                    task_prefix TEXT NOT NULL DEFAULT '',
                    task_group TEXT NOT NULL DEFAULT '',
                    task_geo TEXT NOT NULL DEFAULT '',
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
                    (telegram_id, username, d7_nick, role, wallet, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username      = excluded.username,
                    d7_nick       = excluded.d7_nick,
                    role          = excluded.role,
                    wallet        = excluded.wallet,
                    updated_at    = CURRENT_TIMESTAMP
                """,
                (
                    designer.telegram_id,
                    designer.username,
                    designer.d7_nick,
                    designer.role,
                    designer.wallet,
                ),
            )
            await db.commit()

    async def get_designer(self, telegram_id: int) -> Designer | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT telegram_id, username, d7_nick, role, wallet
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
                SELECT telegram_id, username, d7_nick, role, wallet
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
                INSERT INTO reports
                    (designer_id, report_date, task_code, cost_usdt, payment_status,
                     task_prefix, task_group, task_geo)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    task.designer_id,
                    task.report_date,
                    task.task_code,
                    task.cost_usdt,
                    task.task_prefix,
                    task.task_group,
                    task.task_geo,
                ),
            )
            await db.commit()
        return True

    async def list_tasks_by_date(self, report_date: date) -> list[tuple]:
        """
        Return all tasks for a date.
        Each row: (d7_nick, wallet, task_code, cost_usdt, payment_status)
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT d.d7_nick, d.wallet, r.task_code, r.cost_usdt, r.payment_status
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

    # ── Payment ────────────────────────────────────────────────────────────

    async def update_payment_status(
        self,
        designer_id: int,
        report_date: str,
        status: str,
        paid_by: int,
        payment_comment: str = "",
    ) -> None:
        """Update payment_status for all tasks of a designer for a given date."""
        paid_at = datetime.utcnow().isoformat() if status == "paid" else None
        paid_by_val = paid_by if status == "paid" else None
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE reports
                SET payment_status = ?, paid_at = ?, paid_by = ?, payment_comment = ?
                WHERE designer_id = ? AND report_date = ?
                """,
                (status, paid_at, paid_by_val, payment_comment, designer_id, report_date),
            )
            await db.commit()

    async def get_pending_payments(self) -> list[tuple]:
        """
        Return pending payment summaries grouped by designer+date.
        Each row: (designer_id, d7_nick, wallet, report_date, task_count, total_usdt)
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT r.designer_id, d.d7_nick, d.wallet, r.report_date,
                       COUNT(*) AS task_count, COALESCE(SUM(r.cost_usdt), 0.0) AS total_usdt
                FROM reports r
                JOIN designers d ON d.telegram_id = r.designer_id
                WHERE r.payment_status = 'pending'
                GROUP BY r.designer_id, r.report_date
                ORDER BY r.report_date DESC, d.d7_nick
                """
            )
            return await cursor.fetchall()

    async def get_report_summary(self, designer_id: int, report_date: str) -> dict:
        """
        Return summary for a designer+date:
        {"task_count": int, "total_usdt": float, "payment_status": str}
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(cost_usdt), 0.0),
                       COALESCE(MAX(payment_status), 'pending')
                FROM reports
                WHERE designer_id = ? AND report_date = ?
                """,
                (designer_id, report_date),
            )
            row = await cursor.fetchone()
            if not row or row[0] == 0:
                return {"task_count": 0, "total_usdt": 0.0, "payment_status": "pending"}
            return {
                "task_count": int(row[0]),
                "total_usdt": float(row[1]),
                "payment_status": row[2] or "pending",
            }

    # ── v6 methods ──────────────────────────────────────────────────────────

    async def has_report_for_date(self, designer_id: int, report_date: date) -> bool:
        """Return True if designer has at least one report entry for this date."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM reports WHERE designer_id = ? AND report_date = ? LIMIT 1",
                (designer_id, report_date.isoformat()),
            )
            return await cursor.fetchone() is not None

    async def list_missing_reports(self, report_date: date) -> list[Designer]:
        """Return all designers who have NO report for the given date."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT telegram_id, username, d7_nick, role, wallet
                FROM designers
                WHERE telegram_id NOT IN (
                    SELECT DISTINCT designer_id FROM reports WHERE report_date = ?
                )
                ORDER BY d7_nick
                """,
                (report_date.isoformat(),),
            )
            rows = await cursor.fetchall()
            return [_row_to_designer(r) for r in rows]

    async def get_employee_payment_history(self, designer_id: int) -> dict:
        """
        Return payment history for a designer.
        Returns: paid_count, paid_sum, pending_count, unpaid_count, recent (list of tuples).
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT
                    SUM(CASE WHEN payment_status = 'paid'    THEN 1 ELSE 0 END),
                    SUM(CASE WHEN payment_status = 'paid'    THEN cost_usdt ELSE 0 END),
                    SUM(CASE WHEN payment_status = 'pending' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN payment_status = 'unpaid'  THEN 1 ELSE 0 END)
                FROM reports WHERE designer_id = ?
                """,
                (designer_id,),
            )
            row = await cursor.fetchone()
            paid_count = int(row[0] or 0) if row else 0
            paid_sum = float(row[1] or 0) if row else 0.0
            pending_count = int(row[2] or 0) if row else 0
            unpaid_count = int(row[3] or 0) if row else 0

            cursor2 = await db.execute(
                """
                SELECT report_date, task_code, cost_usdt, payment_status, paid_at
                FROM reports
                WHERE designer_id = ? AND payment_status IN ('paid', 'unpaid')
                ORDER BY COALESCE(paid_at, created_at) DESC
                LIMIT 10
                """,
                (designer_id,),
            )
            recent = await cursor2.fetchall()

            return {
                "paid_count": paid_count,
                "paid_sum": paid_sum,
                "pending_count": pending_count,
                "unpaid_count": unpaid_count,
                "recent": recent,
            }

    async def get_paid_summary(self, since_date: date) -> list[tuple]:
        """
        Return paid payment summaries since `since_date` (Moscow-adjusted via paid_at UTC+3).
        Each row: (designer_id, d7_nick, report_date, task_count, total_usdt)
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT r.designer_id, d.d7_nick, r.report_date,
                       COUNT(*) AS task_count, COALESCE(SUM(r.cost_usdt), 0.0) AS total_usdt
                FROM reports r
                JOIN designers d ON d.telegram_id = r.designer_id
                WHERE r.payment_status = 'paid'
                  AND DATE(r.paid_at, '+3 hours') >= ?
                GROUP BY r.designer_id, r.report_date
                ORDER BY r.report_date DESC, d.d7_nick
                """,
                (since_date.isoformat(),),
            )
            return await cursor.fetchall()

    async def list_designers_by_role(self, role: str | None) -> list[Designer]:
        """Return all designers, optionally filtered by role identifier."""
        async with aiosqlite.connect(self.path) as db:
            if role:
                cursor = await db.execute(
                    """
                    SELECT telegram_id, username, d7_nick, role, wallet
                    FROM designers WHERE role = ? ORDER BY d7_nick
                    """,
                    (role,),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT telegram_id, username, d7_nick, role, wallet
                    FROM designers ORDER BY d7_nick
                    """
                )
            rows = await cursor.fetchall()
            return [_row_to_designer(r) for r in rows]

    # ── v7 Analytics ────────────────────────────────────────────────────────

    async def get_analytics_summary(self, start_date: str, end_date: str) -> dict:
        """
        Return analytics summary for a date range [start_date, end_date] (inclusive).
        Returns:
          {
            "total_usdt": float,
            "geo_usdt": float,    # sum for task_group='geo'
            "visual_usdt": float, # sum for task_group='visual'
            "task_count": int,
          }
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT
                    COALESCE(SUM(cost_usdt), 0.0) AS total_usdt,
                    COALESCE(SUM(CASE WHEN task_group = 'geo'    THEN cost_usdt ELSE 0 END), 0.0) AS geo_usdt,
                    COALESCE(SUM(CASE WHEN task_group = 'visual' THEN cost_usdt ELSE 0 END), 0.0) AS visual_usdt,
                    COUNT(*) AS task_count
                FROM reports
                WHERE report_date >= ? AND report_date <= ?
                """,
                (start_date, end_date),
            )
            row = await cursor.fetchone()
            if not row:
                return {"total_usdt": 0.0, "geo_usdt": 0.0, "visual_usdt": 0.0, "task_count": 0}
            return {
                "total_usdt": float(row[0]),
                "geo_usdt": float(row[1]),
                "visual_usdt": float(row[2]),
                "task_count": int(row[3]),
            }

    async def get_geo_breakdown(self, start_date: str, end_date: str) -> list[dict]:
        """
        Return per-geo breakdown for geo group tasks.
        Returns list of {"geo": str, "usdt": float, "count": int}
        sorted by usdt desc.
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT task_geo,
                       COALESCE(SUM(cost_usdt), 0.0) AS usdt,
                       COUNT(*) AS cnt
                FROM reports
                WHERE report_date >= ? AND report_date <= ?
                  AND task_group = 'geo'
                GROUP BY task_geo
                ORDER BY usdt DESC
                """,
                (start_date, end_date),
            )
            rows = await cursor.fetchall()
            return [{"geo": r[0], "usdt": float(r[1]), "count": int(r[2])} for r in rows]

    async def get_group_breakdown(self, start_date: str, end_date: str) -> list[dict]:
        """
        Return per-group breakdown.
        Returns list of {"group": str, "usdt": float, "count": int}
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT task_group,
                       COALESCE(SUM(cost_usdt), 0.0) AS usdt,
                       COUNT(*) AS cnt
                FROM reports
                WHERE report_date >= ? AND report_date <= ?
                GROUP BY task_group
                ORDER BY usdt DESC
                """,
                (start_date, end_date),
            )
            rows = await cursor.fetchall()
            return [{"group": r[0], "usdt": float(r[1]), "count": int(r[2])} for r in rows]

    # ── v7 Dashboard helpers ─────────────────────────────────────────────────

    async def count_designers_by_role(self) -> dict[str, int]:
        """Return count of designers per role + total."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT role, COUNT(*) FROM designers GROUP BY role
                """
            )
            rows = await cursor.fetchall()
            result: dict[str, int] = {}
            total = 0
            for role, cnt in rows:
                result[role or ""] = cnt
                total += cnt
            result["__total__"] = total
            return result

    async def get_pending_payments_summary(self) -> dict:
        """Return count and total USDT of all pending payment groups."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT COUNT(DISTINCT designer_id || '|' || report_date),
                       COALESCE(SUM(cost_usdt), 0.0)
                FROM reports
                WHERE payment_status = 'pending'
                """
            )
            row = await cursor.fetchone()
            return {
                "count": int(row[0]) if row else 0,
                "total_usdt": float(row[1]) if row else 0.0,
            }

    # ── v8 Analytics ─────────────────────────────────────────────────────────

    async def get_employee_ranking(self, days: int) -> list[dict]:
        """
        Return employee ranking for the last `days` days.
        Each entry: {"d7_nick": str, "role": str, "total_usdt": float, "task_count": int}
        Sorted by total_usdt descending.
        """
        since = (datetime.utcnow().date() - timedelta(days=days - 1)).isoformat()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT d.d7_nick, d.role,
                       COALESCE(SUM(r.cost_usdt), 0.0) AS total_usdt,
                       COUNT(*) AS task_count
                FROM reports r
                JOIN designers d ON d.telegram_id = r.designer_id
                WHERE r.report_date >= ?
                GROUP BY r.designer_id
                ORDER BY total_usdt DESC
                """,
                (since,),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "d7_nick": row[0],
                    "role": row[1] or "",
                    "total_usdt": float(row[2]),
                    "task_count": int(row[3]),
                }
                for row in rows
            ]

    async def get_role_spend_breakdown(self, start_date: str, end_date: str) -> list[dict]:
        """
        Return spend breakdown by designer role.
        Each entry: {"role": str, "total_usdt": float, "task_count": int}
        Sorted by total_usdt descending.
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT d.role,
                       COALESCE(SUM(r.cost_usdt), 0.0) AS total_usdt,
                       COUNT(*) AS task_count
                FROM reports r
                JOIN designers d ON d.telegram_id = r.designer_id
                WHERE r.report_date >= ? AND r.report_date <= ?
                GROUP BY d.role
                ORDER BY total_usdt DESC
                """,
                (start_date, end_date),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "role": row[0] or "",
                    "total_usdt": float(row[1]),
                    "task_count": int(row[2]),
                }
                for row in rows
            ]

    async def get_geo_ranking(self, start_date: str, end_date: str) -> list[dict]:
        """
        Return spend breakdown by task_geo, sorted by total_usdt descending.
        Each entry: {"geo": str, "total_usdt": float, "task_count": int}
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT task_geo,
                       COALESCE(SUM(cost_usdt), 0.0) AS total_usdt,
                       COUNT(*) AS task_count
                FROM reports
                WHERE report_date >= ? AND report_date <= ?
                  AND task_geo != ''
                GROUP BY task_geo
                ORDER BY total_usdt DESC
                """,
                (start_date, end_date),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "geo": row[0],
                    "total_usdt": float(row[1]),
                    "task_count": int(row[2]),
                }
                for row in rows
            ]

    async def get_cost_per_day_breakdown(self, start_date: str, end_date: str) -> list[dict]:
        """
        Return cost-per-day breakdown by task_geo (direction).
        cost_per_day = total_sum / count(distinct report_date) for that geo.
        Each entry: {"geo": str, "total_usdt": float, "day_count": int, "cost_per_day": float}
        Sorted by cost_per_day descending.
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT task_geo,
                       COALESCE(SUM(cost_usdt), 0.0) AS total_usdt,
                       COUNT(DISTINCT report_date) AS day_count
                FROM reports
                WHERE report_date >= ? AND report_date <= ?
                  AND task_geo != ''
                GROUP BY task_geo
                ORDER BY (COALESCE(SUM(cost_usdt), 0.0) / MAX(COUNT(DISTINCT report_date), 1)) DESC
                """,
                (start_date, end_date),
            )
            rows = await cursor.fetchall()
            result = []
            for row in rows:
                geo = row[0]
                total = float(row[1])
                days = int(row[2]) if row[2] else 1
                result.append(
                    {
                        "geo": geo,
                        "total_usdt": total,
                        "day_count": days,
                        "cost_per_day": total / days if days > 0 else 0.0,
                    }
                )
            result.sort(key=lambda x: x["cost_per_day"], reverse=True)
            return result


# ── helpers ────────────────────────────────────────────────────────────────


def _row_to_designer(row: tuple) -> Designer:
    return Designer(
        telegram_id=row[0],
        username=row[1],
        d7_nick=row[2],
        role=row[3] or "",
        wallet=row[4],
    )
