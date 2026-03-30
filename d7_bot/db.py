from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
import zoneinfo

import aiosqlite

logger = logging.getLogger(__name__)
_MOSCOW = zoneinfo.ZoneInfo("Europe/Moscow")


def moscow_today() -> date:
    """Return current calendar date in Europe/Moscow timezone."""
    return datetime.now(tz=_MOSCOW).date()


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(tz=timezone.utc).isoformat()


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


@dataclass
class ReviewerEntry:
    subject_user_id: int
    entered_by_user_id: int
    report_date: str
    review_geo: str
    review_count: int
    unit_price: float
    comment: str = ""

    @property
    def cost_usdt(self) -> float:
        return float(self.review_count) * float(self.unit_price)


@dataclass
class SmmDailyEntry:
    subject_user_id: int
    entered_by_user_id: int
    report_date: str
    fixed_day_amount: float
    comment: str = ""

    @property
    def cost_usdt(self) -> float:
        return float(self.fixed_day_amount)


@dataclass
class Employee:
    id: int
    telegram_id: int | None
    username: str | None
    display_name: str
    role: str
    wallet: str
    is_active: bool


@dataclass
class SmmAssignment:
    id: int
    smm_employee_id: int
    channel_name: str
    geo: str
    daily_rate_usdt: float
    active_from: str | None
    active_to: str | None
    status: str
    comment: str


@dataclass
class ReviewEntryItem:
    review_type: str
    quantity: int
    unit_price: float
    total_usdt: float
    comment: str = ""


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

            # v2 groundwork: universal report entry fields
            cursor = await db.execute("PRAGMA table_info(reports)")
            report_cols = {row[1] for row in await cursor.fetchall()}

            if report_cols and "entry_type" not in report_cols:
                logger.info("Migrating reports table: adding entry_type column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN entry_type TEXT NOT NULL DEFAULT 'designer_task'"
                )
                await db.commit()

            if report_cols and "subject_user_id" not in report_cols:
                logger.info("Migrating reports table: adding subject_user_id column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN subject_user_id INTEGER"
                )
                await db.commit()

            if report_cols and "entered_by_user_id" not in report_cols:
                logger.info("Migrating reports table: adding entered_by_user_id column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN entered_by_user_id INTEGER"
                )
                await db.commit()

            if report_cols and "comment" not in report_cols:
                logger.info("Migrating reports table: adding comment column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN comment TEXT NOT NULL DEFAULT ''"
                )
                await db.commit()

            if report_cols and "review_geo" not in report_cols:
                logger.info("Migrating reports table: adding review_geo column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN review_geo TEXT NOT NULL DEFAULT ''"
                )
                await db.commit()

            if report_cols and "review_count" not in report_cols:
                logger.info("Migrating reports table: adding review_count column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN review_count INTEGER NOT NULL DEFAULT 0"
                )
                await db.commit()

            if report_cols and "unit_price" not in report_cols:
                logger.info("Migrating reports table: adding unit_price column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN unit_price REAL NOT NULL DEFAULT 0"
                )
                await db.commit()

            if report_cols and "fixed_day_amount" not in report_cols:
                logger.info("Migrating reports table: adding fixed_day_amount column")
                await db.execute(
                    "ALTER TABLE reports ADD COLUMN fixed_day_amount REAL NOT NULL DEFAULT 0"
                )
                await db.commit()

            await db.execute(
                """
                UPDATE reports
                SET subject_user_id = COALESCE(subject_user_id, designer_id),
                    entered_by_user_id = COALESCE(entered_by_user_id, designer_id),
                    entry_type = COALESCE(NULLIF(entry_type, ''), 'designer_task')
                """
            )
            await db.commit()

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

            # v9: new domain model groundwork (kept alongside legacy tables)
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    username TEXT,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    wallet TEXT NOT NULL DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS smm_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    smm_employee_id INTEGER NOT NULL,
                    channel_name TEXT NOT NULL,
                    geo TEXT NOT NULL DEFAULT '',
                    daily_rate_usdt REAL NOT NULL DEFAULT 0,
                    active_from TEXT,
                    active_to TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (smm_employee_id) REFERENCES employees(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS review_rate_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_type TEXT NOT NULL UNIQUE,
                    default_unit_price REAL NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS review_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL,
                    report_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'submitted',
                    verified_by_pm INTEGER,
                    verified_at TEXT,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
                    FOREIGN KEY (verified_by_pm) REFERENCES employees(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS review_entry_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_entry_id INTEGER NOT NULL,
                    review_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    unit_price REAL NOT NULL DEFAULT 0,
                    total_usdt REAL NOT NULL DEFAULT 0,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (review_entry_id) REFERENCES review_entries(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS smm_daily_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    smm_employee_id INTEGER NOT NULL,
                    entered_by_pm_id INTEGER NOT NULL,
                    report_date TEXT NOT NULL,
                    assignment_id INTEGER,
                    channel_name_snapshot TEXT NOT NULL DEFAULT '',
                    geo_snapshot TEXT NOT NULL DEFAULT '',
                    daily_rate_snapshot REAL NOT NULL DEFAULT 0,
                    total_usdt REAL NOT NULL DEFAULT 0,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (smm_employee_id) REFERENCES employees(id) ON DELETE CASCADE,
                    FOREIGN KEY (entered_by_pm_id) REFERENCES employees(id) ON DELETE CASCADE,
                    FOREIGN KEY (assignment_id) REFERENCES smm_assignments(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS payment_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL,
                    payout_mode TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    period_start TEXT,
                    period_end TEXT,
                    total_usdt REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    paid_at TEXT,
                    paid_by INTEGER,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
                    FOREIGN KEY (paid_by) REFERENCES employees(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS payment_batch_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id INTEGER NOT NULL,
                    source_table TEXT NOT NULL,
                    source_entry_id INTEGER NOT NULL,
                    amount_usdt REAL NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (batch_id) REFERENCES payment_batches(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_employees_role ON employees(role);
                CREATE INDEX IF NOT EXISTS idx_smm_assignments_employee ON smm_assignments(smm_employee_id);
                CREATE INDEX IF NOT EXISTS idx_review_entries_employee_date ON review_entries(employee_id, report_date);
                CREATE INDEX IF NOT EXISTS idx_smm_daily_entries_employee_date ON smm_daily_entries(smm_employee_id, report_date);
                CREATE INDEX IF NOT EXISTS idx_payment_batches_employee_status ON payment_batches(employee_id, status);
            """)

            # Bootstrap employees from legacy designers table.
            await db.execute("""
                INSERT INTO employees (telegram_id, username, display_name, role, wallet)
                SELECT d.telegram_id, d.username, d.d7_nick, d.role, d.wallet
                FROM designers d
                WHERE NOT EXISTS (
                    SELECT 1 FROM employees e WHERE e.telegram_id = d.telegram_id
                )
            """)

            # Seed baseline reviewer rate rules.
            await db.executescript("""
                INSERT OR IGNORE INTO review_rate_rules (review_type, default_unit_price, comment)
                VALUES ('small', 0, 'Default small review rate');
                INSERT OR IGNORE INTO review_rate_rules (review_type, default_unit_price, comment)
                VALUES ('large', 0, 'Default large review rate');
                INSERT OR IGNORE INTO review_rate_rules (review_type, default_unit_price, comment)
                VALUES ('custom', 0, 'Custom reviewer rate');
            """)
            await db.commit()

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
                    subject_user_id INTEGER,
                    entered_by_user_id INTEGER,
                    entry_type TEXT NOT NULL DEFAULT 'designer_task',
                    report_date TEXT NOT NULL,
                    task_code TEXT NOT NULL,
                    cost_usdt REAL NOT NULL,
                    payment_status TEXT DEFAULT 'pending',
                    paid_at TEXT,
                    paid_by INTEGER,
                    payment_comment TEXT DEFAULT '',
                    comment TEXT NOT NULL DEFAULT '',
                    task_prefix TEXT NOT NULL DEFAULT '',
                    task_group TEXT NOT NULL DEFAULT '',
                    task_geo TEXT NOT NULL DEFAULT '',
                    review_geo TEXT NOT NULL DEFAULT '',
                    review_count INTEGER NOT NULL DEFAULT 0,
                    unit_price REAL NOT NULL DEFAULT 0,
                    fixed_day_amount REAL NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (designer_id) REFERENCES designers(telegram_id) ON DELETE CASCADE,
                    UNIQUE(designer_id, report_date, task_code)
                );

                CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date);
                CREATE INDEX IF NOT EXISTS idx_reports_designer ON reports(designer_id);

                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    username TEXT,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    wallet TEXT NOT NULL DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS smm_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    smm_employee_id INTEGER NOT NULL,
                    channel_name TEXT NOT NULL,
                    geo TEXT NOT NULL DEFAULT '',
                    daily_rate_usdt REAL NOT NULL DEFAULT 0,
                    active_from TEXT,
                    active_to TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (smm_employee_id) REFERENCES employees(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS review_rate_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_type TEXT NOT NULL UNIQUE,
                    default_unit_price REAL NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS review_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL,
                    report_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'submitted',
                    verified_by_pm INTEGER,
                    verified_at TEXT,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
                    FOREIGN KEY (verified_by_pm) REFERENCES employees(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS review_entry_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_entry_id INTEGER NOT NULL,
                    review_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    unit_price REAL NOT NULL DEFAULT 0,
                    total_usdt REAL NOT NULL DEFAULT 0,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (review_entry_id) REFERENCES review_entries(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS smm_daily_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    smm_employee_id INTEGER NOT NULL,
                    entered_by_pm_id INTEGER NOT NULL,
                    report_date TEXT NOT NULL,
                    assignment_id INTEGER,
                    channel_name_snapshot TEXT NOT NULL DEFAULT '',
                    geo_snapshot TEXT NOT NULL DEFAULT '',
                    daily_rate_snapshot REAL NOT NULL DEFAULT 0,
                    total_usdt REAL NOT NULL DEFAULT 0,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (smm_employee_id) REFERENCES employees(id) ON DELETE CASCADE,
                    FOREIGN KEY (entered_by_pm_id) REFERENCES employees(id) ON DELETE CASCADE,
                    FOREIGN KEY (assignment_id) REFERENCES smm_assignments(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS payment_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL,
                    payout_mode TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    period_start TEXT,
                    period_end TEXT,
                    total_usdt REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    paid_at TEXT,
                    paid_by INTEGER,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
                    FOREIGN KEY (paid_by) REFERENCES employees(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS payment_batch_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id INTEGER NOT NULL,
                    source_table TEXT NOT NULL,
                    source_entry_id INTEGER NOT NULL,
                    amount_usdt REAL NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (batch_id) REFERENCES payment_batches(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_employees_role ON employees(role);
                CREATE INDEX IF NOT EXISTS idx_smm_assignments_employee ON smm_assignments(smm_employee_id);
                CREATE INDEX IF NOT EXISTS idx_review_entries_employee_date ON review_entries(employee_id, report_date);
                CREATE INDEX IF NOT EXISTS idx_smm_daily_entries_employee_date ON smm_daily_entries(smm_employee_id, report_date);
                CREATE INDEX IF NOT EXISTS idx_payment_batches_employee_status ON payment_batches(employee_id, status);
            """)
            await db.commit()

        # Run migration after table creation (in case of old schema)
        await self.migrate()

    # ── Employees (next-gen domain model) ─────────────────────────────────

    async def list_employees_by_role(self, role: str | None = None) -> list[Employee]:
        async with aiosqlite.connect(self.path) as db:
            if role:
                cursor = await db.execute(
                    """
                    SELECT id, telegram_id, username, display_name, role, wallet, is_active
                    FROM employees
                    WHERE role = ? AND is_active = 1
                    ORDER BY display_name COLLATE NOCASE
                    """,
                    (role,),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT id, telegram_id, username, display_name, role, wallet, is_active
                    FROM employees
                    WHERE is_active = 1
                    ORDER BY display_name COLLATE NOCASE
                    """
                )
            rows = await cursor.fetchall()
            return [_row_to_employee(row) for row in rows]

    async def get_employee_by_telegram_id(self, telegram_id: int) -> Employee | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT id, telegram_id, username, display_name, role, wallet, is_active
                FROM employees
                WHERE telegram_id = ?
                LIMIT 1
                """,
                (telegram_id,),
            )
            row = await cursor.fetchone()
            return _row_to_employee(row) if row else None

    async def get_employee(self, employee_id: int) -> Employee | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT id, telegram_id, username, display_name, role, wallet, is_active
                FROM employees
                WHERE id = ?
                LIMIT 1
                """,
                (employee_id,),
            )
            row = await cursor.fetchone()
            return _row_to_employee(row) if row else None

    async def add_smm_assignment(
        self,
        smm_employee_id: int,
        channel_name: str,
        geo: str,
        daily_rate_usdt: float,
        active_from: str | None = None,
        active_to: str | None = None,
        comment: str = "",
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                INSERT INTO smm_assignments
                    (smm_employee_id, channel_name, geo, daily_rate_usdt, active_from, active_to, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (smm_employee_id, channel_name, geo, daily_rate_usdt, active_from, active_to, comment),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def list_active_smm_assignments(self, smm_employee_id: int | None = None) -> list[SmmAssignment]:
        async with aiosqlite.connect(self.path) as db:
            if smm_employee_id is not None:
                cursor = await db.execute(
                    """
                    SELECT id, smm_employee_id, channel_name, geo, daily_rate_usdt,
                           active_from, active_to, status, comment
                    FROM smm_assignments
                    WHERE smm_employee_id = ? AND status = 'active'
                    ORDER BY channel_name COLLATE NOCASE
                    """,
                    (smm_employee_id,),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT id, smm_employee_id, channel_name, geo, daily_rate_usdt,
                           active_from, active_to, status, comment
                    FROM smm_assignments
                    WHERE status = 'active'
                    ORDER BY smm_employee_id, channel_name COLLATE NOCASE
                    """
                )
            rows = await cursor.fetchall()
            return [_row_to_smm_assignment(row) for row in rows]

    async def list_active_smm_assignments_detailed(self) -> list[tuple[SmmAssignment, Employee]]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT a.id, a.smm_employee_id, a.channel_name, a.geo, a.daily_rate_usdt,
                       a.active_from, a.active_to, a.status, a.comment,
                       e.id, e.telegram_id, e.username, e.display_name, e.role, e.wallet, e.is_active
                FROM smm_assignments a
                JOIN employees e ON e.id = a.smm_employee_id
                WHERE a.status = 'active' AND e.is_active = 1
                ORDER BY e.display_name COLLATE NOCASE, a.channel_name COLLATE NOCASE
                """
            )
            rows = await cursor.fetchall()
            return [(_row_to_smm_assignment(row[:9]), _row_to_employee(row[9:16])) for row in rows]

    async def add_smm_daily_entry_v2(
        self,
        smm_employee_id: int,
        entered_by_pm_id: int,
        report_date: str,
        assignment_id: int,
        channel_name_snapshot: str,
        geo_snapshot: str,
        daily_rate_snapshot: float,
        comment: str = "",
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                INSERT INTO smm_daily_entries
                    (smm_employee_id, entered_by_pm_id, report_date, assignment_id,
                     channel_name_snapshot, geo_snapshot, daily_rate_snapshot, total_usdt, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    smm_employee_id,
                    entered_by_pm_id,
                    report_date,
                    assignment_id,
                    channel_name_snapshot,
                    geo_snapshot,
                    daily_rate_snapshot,
                    daily_rate_snapshot,
                    comment,
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def get_smm_weekly_summary(self, period_start: str, period_end: str) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT e.id, e.display_name,
                       COUNT(s.id) AS entry_count,
                       COUNT(DISTINCT s.report_date) AS day_count,
                       COALESCE(SUM(s.total_usdt), 0.0) AS total_usdt
                FROM smm_daily_entries s
                JOIN employees e ON e.id = s.smm_employee_id
                WHERE s.report_date >= ? AND s.report_date <= ?
                GROUP BY e.id, e.display_name
                ORDER BY total_usdt DESC, e.display_name COLLATE NOCASE
                """,
                (period_start, period_end),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "employee_id": int(row[0]),
                    "display_name": row[1],
                    "entry_count": int(row[2]),
                    "day_count": int(row[3]),
                    "total_usdt": float(row[4]),
                }
                for row in rows
            ]

    async def get_smm_weekly_details(self, employee_id: int, period_start: str, period_end: str) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT report_date, channel_name_snapshot, geo_snapshot, daily_rate_snapshot, total_usdt, comment
                FROM smm_daily_entries
                WHERE smm_employee_id = ? AND report_date >= ? AND report_date <= ?
                ORDER BY report_date ASC, channel_name_snapshot COLLATE NOCASE
                """,
                (employee_id, period_start, period_end),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "report_date": row[0],
                    "channel_name": row[1],
                    "geo": row[2] or "",
                    "daily_rate": float(row[3] or 0),
                    "total_usdt": float(row[4] or 0),
                    "comment": row[5] or "",
                }
                for row in rows
            ]

    async def create_smm_weekly_batches(self, period_start: str, period_end: str) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT e.id, e.display_name,
                       COALESCE(SUM(s.total_usdt), 0.0) AS total_usdt
                FROM smm_daily_entries s
                JOIN employees e ON e.id = s.smm_employee_id
                WHERE s.report_date >= ? AND s.report_date <= ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM payment_batch_items pbi
                      JOIN payment_batches pb ON pb.id = pbi.batch_id
                      WHERE pbi.source_table = 'smm_daily_entries'
                        AND pbi.source_entry_id = s.id
                        AND pb.status IN ('pending', 'paid')
                  )
                GROUP BY e.id, e.display_name
                HAVING total_usdt > 0
                ORDER BY e.display_name COLLATE NOCASE
                """,
                (period_start, period_end),
            )
            employees = await cursor.fetchall()

            created: list[dict] = []
            for employee_id, display_name, total_usdt in employees:
                batch_cursor = await db.execute(
                    """
                    INSERT INTO payment_batches
                        (employee_id, payout_mode, source_type, period_start, period_end, total_usdt, status)
                    VALUES (?, 'weekly', 'smm', ?, ?, ?, 'pending')
                    """,
                    (employee_id, period_start, period_end, float(total_usdt)),
                )
                batch_id = int(batch_cursor.lastrowid)

                item_cursor = await db.execute(
                    """
                    SELECT id, total_usdt
                    FROM smm_daily_entries s
                    WHERE s.smm_employee_id = ?
                      AND s.report_date >= ? AND s.report_date <= ?
                      AND NOT EXISTS (
                          SELECT 1
                          FROM payment_batch_items pbi
                          JOIN payment_batches pb ON pb.id = pbi.batch_id
                          WHERE pbi.source_table = 'smm_daily_entries'
                            AND pbi.source_entry_id = s.id
                            AND pb.id != ?
                            AND pb.status IN ('pending', 'paid')
                      )
                    """,
                    (employee_id, period_start, period_end, batch_id),
                )
                items = await item_cursor.fetchall()
                for entry_id, amount_usdt in items:
                    await db.execute(
                        """
                        INSERT INTO payment_batch_items
                            (batch_id, source_table, source_entry_id, amount_usdt)
                        VALUES (?, 'smm_daily_entries', ?, ?)
                        """,
                        (batch_id, entry_id, float(amount_usdt or 0)),
                    )

                created.append(
                    {
                        'batch_id': batch_id,
                        'employee_id': int(employee_id),
                        'display_name': display_name,
                        'total_usdt': float(total_usdt),
                    }
                )

            await db.commit()
            return created

    async def list_pending_smm_batches(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT pb.id, pb.employee_id, e.display_name, pb.period_start, pb.period_end,
                       pb.total_usdt, COUNT(pbi.id) AS item_count
                FROM payment_batches pb
                JOIN employees e ON e.id = pb.employee_id
                LEFT JOIN payment_batch_items pbi ON pbi.batch_id = pb.id
                WHERE pb.source_type = 'smm' AND pb.payout_mode = 'weekly' AND pb.status = 'pending'
                GROUP BY pb.id, pb.employee_id, e.display_name, pb.period_start, pb.period_end, pb.total_usdt
                ORDER BY pb.created_at DESC, e.display_name COLLATE NOCASE
                """
            )
            rows = await cursor.fetchall()
            return [
                {
                    'batch_id': int(row[0]),
                    'employee_id': int(row[1]),
                    'display_name': row[2],
                    'period_start': row[3],
                    'period_end': row[4],
                    'total_usdt': float(row[5]),
                    'item_count': int(row[6]),
                }
                for row in rows
            ]

    async def mark_smm_batch_paid(self, batch_id: int, paid_by_employee_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT pb.id, pb.employee_id, e.display_name, pb.period_start, pb.period_end, pb.total_usdt, pb.status
                FROM payment_batches pb
                JOIN employees e ON e.id = pb.employee_id
                WHERE pb.id = ? AND pb.source_type = 'smm' AND pb.payout_mode = 'weekly'
                LIMIT 1
                """,
                (batch_id,),
            )
            row = await cursor.fetchone()
            if not row or row[6] != 'pending':
                return None

            await db.execute(
                """
                UPDATE payment_batches
                SET status = 'paid', paid_at = ?, paid_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (utc_now_iso(), paid_by_employee_id, batch_id),
            )
            await db.commit()
            return {
                'batch_id': int(row[0]),
                'employee_id': int(row[1]),
                'display_name': row[2],
                'period_start': row[3],
                'period_end': row[4],
                'total_usdt': float(row[5]),
            }

    async def list_recent_smm_batches(self, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT pb.id, pb.employee_id, e.display_name, pb.period_start, pb.period_end,
                       pb.total_usdt, pb.status, pb.paid_at, COUNT(pbi.id) AS item_count
                FROM payment_batches pb
                JOIN employees e ON e.id = pb.employee_id
                LEFT JOIN payment_batch_items pbi ON pbi.batch_id = pb.id
                WHERE pb.source_type = 'smm' AND pb.payout_mode = 'weekly'
                GROUP BY pb.id, pb.employee_id, e.display_name, pb.period_start, pb.period_end, pb.total_usdt, pb.status, pb.paid_at
                ORDER BY COALESCE(pb.paid_at, pb.created_at) DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [
                {
                    'batch_id': int(row[0]),
                    'employee_id': int(row[1]),
                    'display_name': row[2],
                    'period_start': row[3],
                    'period_end': row[4],
                    'total_usdt': float(row[5]),
                    'status': row[6],
                    'paid_at': row[7],
                    'item_count': int(row[8]),
                }
                for row in rows
            ]

    async def list_review_rate_rules(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT review_type, default_unit_price, comment
                FROM review_rate_rules
                WHERE is_active = 1
                ORDER BY review_type COLLATE NOCASE
                """
            )
            rows = await cursor.fetchall()
            return [
                {
                    'review_type': row[0],
                    'default_unit_price': float(row[1] or 0),
                    'comment': row[2] or '',
                }
                for row in rows
            ]

    async def create_review_entry_v2(
        self,
        employee_id: int,
        report_date: str,
        items: list[ReviewEntryItem],
        comment: str = '',
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                INSERT INTO review_entries (employee_id, report_date, status, comment)
                VALUES (?, ?, 'submitted', ?)
                """,
                (employee_id, report_date, comment),
            )
            review_entry_id = int(cursor.lastrowid)
            for item in items:
                await db.execute(
                    """
                    INSERT INTO review_entry_items
                        (review_entry_id, review_type, quantity, unit_price, total_usdt, comment)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_entry_id,
                        item.review_type,
                        item.quantity,
                        item.unit_price,
                        item.total_usdt,
                        item.comment,
                    ),
                )
            await db.commit()
            return review_entry_id

    async def get_review_entry_summary(self, review_entry_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT re.id, re.employee_id, e.display_name, re.report_date, re.status,
                       COALESCE(SUM(ri.total_usdt), 0.0) AS total_usdt,
                       COUNT(ri.id) AS item_count
                FROM review_entries re
                JOIN employees e ON e.id = re.employee_id
                LEFT JOIN review_entry_items ri ON ri.review_entry_id = re.id
                WHERE re.id = ?
                GROUP BY re.id, re.employee_id, e.display_name, re.report_date, re.status
                LIMIT 1
                """,
                (review_entry_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                'review_entry_id': int(row[0]),
                'employee_id': int(row[1]),
                'display_name': row[2],
                'report_date': row[3],
                'status': row[4],
                'total_usdt': float(row[5]),
                'item_count': int(row[6]),
            }

    async def list_pending_review_entries(self, limit: int = 20) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT re.id, re.employee_id, e.display_name, re.report_date,
                       COALESCE(SUM(ri.total_usdt), 0.0) AS total_usdt,
                       COUNT(ri.id) AS item_count
                FROM review_entries re
                JOIN employees e ON e.id = re.employee_id
                LEFT JOIN review_entry_items ri ON ri.review_entry_id = re.id
                WHERE re.status = 'submitted'
                GROUP BY re.id, re.employee_id, e.display_name, re.report_date
                ORDER BY re.created_at ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [
                {
                    'review_entry_id': int(row[0]),
                    'employee_id': int(row[1]),
                    'display_name': row[2],
                    'report_date': row[3],
                    'total_usdt': float(row[4]),
                    'item_count': int(row[5]),
                }
                for row in rows
            ]

    async def verify_review_entry(self, review_entry_id: int, pm_employee_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            summary = await self.get_review_entry_summary(review_entry_id)
            if not summary or summary['status'] != 'submitted':
                return None
            await db.execute(
                """
                UPDATE review_entries
                SET status = 'verified', verified_by_pm = ?, verified_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (pm_employee_id, utc_now_iso(), review_entry_id),
            )
            await db.commit()
            summary['status'] = 'verified'
            return summary

    async def reject_review_entry(self, review_entry_id: int, pm_employee_id: int, comment: str = '') -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            summary = await self.get_review_entry_summary(review_entry_id)
            if not summary or summary['status'] != 'submitted':
                return None
            await db.execute(
                """
                UPDATE review_entries
                SET status = 'rejected', verified_by_pm = ?, verified_at = ?,
                    comment = CASE WHEN ? = '' THEN comment ELSE ? END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (pm_employee_id, utc_now_iso(), comment, comment, review_entry_id),
            )
            await db.commit()
            summary['status'] = 'rejected'
            return summary

    async def create_reviewer_payout_batches(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT re.id, re.employee_id, e.display_name, re.report_date,
                       COALESCE(SUM(ri.total_usdt), 0.0) AS total_usdt
                FROM review_entries re
                JOIN employees e ON e.id = re.employee_id
                LEFT JOIN review_entry_items ri ON ri.review_entry_id = re.id
                WHERE re.status = 'verified'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM payment_batch_items pbi
                      JOIN payment_batches pb ON pb.id = pbi.batch_id
                      WHERE pbi.source_table = 'review_entries'
                        AND pbi.source_entry_id = re.id
                        AND pb.status IN ('pending', 'paid')
                  )
                GROUP BY re.id, re.employee_id, e.display_name, re.report_date
                HAVING total_usdt > 0
                ORDER BY re.report_date ASC, e.display_name COLLATE NOCASE
                """
            )
            rows = await cursor.fetchall()
            created: list[dict] = []
            for review_entry_id, employee_id, display_name, report_date, total_usdt in rows:
                batch_cursor = await db.execute(
                    """
                    INSERT INTO payment_batches
                        (employee_id, payout_mode, source_type, period_start, period_end, total_usdt, status)
                    VALUES (?, 'immediate', 'reviewer', ?, ?, ?, 'pending')
                    """,
                    (employee_id, report_date, report_date, float(total_usdt)),
                )
                batch_id = int(batch_cursor.lastrowid)
                await db.execute(
                    """
                    INSERT INTO payment_batch_items
                        (batch_id, source_table, source_entry_id, amount_usdt)
                    VALUES (?, 'review_entries', ?, ?)
                    """,
                    (batch_id, int(review_entry_id), float(total_usdt)),
                )
                created.append(
                    {
                        'batch_id': batch_id,
                        'employee_id': int(employee_id),
                        'display_name': display_name,
                        'report_date': report_date,
                        'total_usdt': float(total_usdt),
                        'review_entry_id': int(review_entry_id),
                    }
                )
            await db.commit()
            return created

    async def list_pending_reviewer_batches(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT pb.id, pb.employee_id, e.display_name, pb.period_start, pb.period_end,
                       pb.total_usdt, COUNT(pbi.id) AS item_count
                FROM payment_batches pb
                JOIN employees e ON e.id = pb.employee_id
                LEFT JOIN payment_batch_items pbi ON pbi.batch_id = pb.id
                WHERE pb.source_type = 'reviewer' AND pb.payout_mode = 'immediate' AND pb.status = 'pending'
                GROUP BY pb.id, pb.employee_id, e.display_name, pb.period_start, pb.period_end, pb.total_usdt
                ORDER BY pb.created_at DESC, e.display_name COLLATE NOCASE
                """
            )
            rows = await cursor.fetchall()
            return [
                {
                    'batch_id': int(row[0]),
                    'employee_id': int(row[1]),
                    'display_name': row[2],
                    'period_start': row[3],
                    'period_end': row[4],
                    'total_usdt': float(row[5]),
                    'item_count': int(row[6]),
                }
                for row in rows
            ]

    async def mark_reviewer_batch_paid(self, batch_id: int, paid_by_employee_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT pb.id, pb.employee_id, e.display_name, pb.period_start, pb.period_end, pb.total_usdt, pb.status
                FROM payment_batches pb
                JOIN employees e ON e.id = pb.employee_id
                WHERE pb.id = ? AND pb.source_type = 'reviewer' AND pb.payout_mode = 'immediate'
                LIMIT 1
                """,
                (batch_id,),
            )
            row = await cursor.fetchone()
            if not row or row[6] != 'pending':
                return None
            await db.execute(
                """
                UPDATE payment_batches
                SET status = 'paid', paid_at = ?, paid_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (utc_now_iso(), paid_by_employee_id, batch_id),
            )
            await db.commit()
            return {
                'batch_id': int(row[0]),
                'employee_id': int(row[1]),
                'display_name': row[2],
                'period_start': row[3],
                'period_end': row[4],
                'total_usdt': float(row[5]),
            }

    async def list_recent_reviewer_batches(self, limit: int = 15) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT pb.id, pb.employee_id, e.display_name, pb.period_start, pb.period_end,
                       pb.total_usdt, pb.status, pb.paid_at, COUNT(pbi.id) AS item_count
                FROM payment_batches pb
                JOIN employees e ON e.id = pb.employee_id
                LEFT JOIN payment_batch_items pbi ON pbi.batch_id = pb.id
                WHERE pb.source_type = 'reviewer' AND pb.payout_mode = 'immediate'
                GROUP BY pb.id, pb.employee_id, e.display_name, pb.period_start, pb.period_end, pb.total_usdt, pb.status, pb.paid_at
                ORDER BY COALESCE(pb.paid_at, pb.created_at) DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [
                {
                    'batch_id': int(row[0]),
                    'employee_id': int(row[1]),
                    'display_name': row[2],
                    'period_start': row[3],
                    'period_end': row[4],
                    'total_usdt': float(row[5]),
                    'status': row[6],
                    'paid_at': row[7],
                    'item_count': int(row[8]),
                }
                for row in rows
            ]

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
                    (designer_id, subject_user_id, entered_by_user_id, entry_type,
                     report_date, task_code, cost_usdt, payment_status,
                     task_prefix, task_group, task_geo)
                VALUES (?, ?, ?, 'designer_task', ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    task.designer_id,
                    task.designer_id,
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
        Return tasks for *designer_id* over the last *days* days (inclusive today, Moscow time).
        Each row: (report_date, task_code, cost_usdt)
        """
        since = (moscow_today() - timedelta(days=days - 1)).isoformat()
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
        Return statistics for a designer over the last *days* days (Moscow time).
        Returns {"task_count": int, "total_usdt": float}
        """
        since = (moscow_today() - timedelta(days=days - 1)).isoformat()
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

    async def list_designer_reports(self, designer_id: int, limit: int = 50) -> list[tuple]:
        """
        Return recent task rows for a designer.
        Each row: (report_date, task_code, cost_usdt, payment_status, payment_comment)
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT report_date, task_code, cost_usdt, payment_status, COALESCE(payment_comment, '')
                FROM reports
                WHERE designer_id = ?
                ORDER BY report_date DESC, id DESC
                LIMIT ?
                """,
                (designer_id, limit),
            )
            return await cursor.fetchall()

    async def get_designer_payment_summary(self, designer_id: int) -> dict:
        """
        Return grouped payment summary for a designer across all reports.
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN cost_usdt ELSE 0 END), 0.0),
                    COALESCE(SUM(CASE WHEN payment_status = 'pending' THEN cost_usdt ELSE 0 END), 0.0),
                    COUNT(*)
                FROM reports
                WHERE designer_id = ?
                """,
                (designer_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return {"paid_usdt": 0.0, "pending_usdt": 0.0, "report_count": 0}
            return {
                "paid_usdt": float(row[0]),
                "pending_usdt": float(row[1]),
                "report_count": int(row[2]),
            }

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
        paid_at = utc_now_iso() if status == "paid" else None
        paid_by_val = paid_by if status == "paid" else None
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE reports
                SET payment_status = ?, paid_at = ?, paid_by = ?, payment_comment = ?
                WHERE COALESCE(subject_user_id, designer_id) = ? AND report_date = ?
                """,
                (status, paid_at, paid_by_val, payment_comment, designer_id, report_date),
            )
            await db.commit()

    async def get_pending_payments(self) -> list[tuple]:
        """
        Return pending payment summaries grouped by subject_user_id+date.
        Each row: (designer_id, d7_nick, wallet, report_date, task_count, total_usdt)
        """
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT COALESCE(r.subject_user_id, r.designer_id) AS subject_user_id,
                       d.d7_nick, d.wallet, r.report_date,
                       COUNT(*) AS task_count, COALESCE(SUM(r.cost_usdt), 0.0) AS total_usdt
                FROM reports r
                JOIN designers d ON d.telegram_id = COALESCE(r.subject_user_id, r.designer_id)
                WHERE r.payment_status = 'pending'
                GROUP BY COALESCE(r.subject_user_id, r.designer_id), r.report_date
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
        """Return designers-only employees who have NO report for the given date."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT telegram_id, username, d7_nick, role, wallet
                FROM designers
                WHERE role = 'designer'
                  AND telegram_id NOT IN (
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
                JOIN designers d ON d.telegram_id = COALESCE(r.subject_user_id, r.designer_id)
                WHERE r.payment_status = 'paid'
                  AND DATE(r.paid_at, '+3 hours') >= ?
                GROUP BY COALESCE(r.subject_user_id, r.designer_id), r.report_date
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
        Return employee ranking for the last `days` days (Moscow time).
        Each entry: {"d7_nick": str, "role": str, "total_usdt": float, "task_count": int}
        Sorted by total_usdt descending.
        """
        since = (moscow_today() - timedelta(days=days - 1)).isoformat()
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


    # ── role-specific report entries ───────────────────────────────────────

    async def add_reviewer_entry(self, entry: ReviewerEntry) -> bool:
        task_code = f"reviews:{entry.review_geo}:{entry.review_count}"
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM reports WHERE designer_id = ? AND report_date = ? AND task_code = ? LIMIT 1",
                (entry.subject_user_id, entry.report_date, task_code),
            )
            exists = await cursor.fetchone()
            if exists:
                return False
            await db.execute(
                """
                INSERT INTO reports
                    (designer_id, subject_user_id, entered_by_user_id, entry_type,
                     report_date, task_code, cost_usdt, payment_status,
                     comment, review_geo, review_count, unit_price)
                VALUES (?, ?, ?, 'reviewer_piecework', ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    entry.subject_user_id,
                    entry.subject_user_id,
                    entry.entered_by_user_id,
                    entry.report_date,
                    task_code,
                    entry.cost_usdt,
                    entry.comment,
                    entry.review_geo,
                    entry.review_count,
                    entry.unit_price,
                ),
            )
            await db.commit()
            return True


    async def add_smm_daily_entry(self, entry: SmmDailyEntry) -> bool:
        task_code = "smm_daily_fixed"
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM reports WHERE entry_type = 'smm_daily_fixed' AND COALESCE(subject_user_id, designer_id) = ? AND report_date = ? LIMIT 1",
                (entry.subject_user_id, entry.report_date),
            )
            exists = await cursor.fetchone()
            if exists:
                return False
            await db.execute(
                """
                INSERT INTO reports
                    (designer_id, subject_user_id, entered_by_user_id, entry_type,
                     report_date, task_code, cost_usdt, payment_status,
                     comment, fixed_day_amount)
                VALUES (?, ?, ?, 'smm_daily_fixed', ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    entry.subject_user_id,
                    entry.subject_user_id,
                    entry.entered_by_user_id,
                    entry.report_date,
                    task_code,
                    entry.cost_usdt,
                    entry.comment,
                    entry.fixed_day_amount,
                ),
            )
            await db.commit()
            return True

def _row_to_designer(row: tuple) -> Designer:
    return Designer(
        telegram_id=row[0],
        username=row[1],
        d7_nick=row[2],
        role=row[3] or "",
        wallet=row[4],
    )


def _row_to_employee(row: tuple) -> Employee:
    return Employee(
        id=int(row[0]),
        telegram_id=row[1],
        username=row[2],
        display_name=row[3],
        role=row[4] or "",
        wallet=row[5] or "",
        is_active=bool(row[6]),
    )


def _row_to_smm_assignment(row: tuple) -> SmmAssignment:
    return SmmAssignment(
        id=int(row[0]),
        smm_employee_id=int(row[1]),
        channel_name=row[2],
        geo=row[3] or "",
        daily_rate_usdt=float(row[4] or 0),
        active_from=row[5],
        active_to=row[6],
        status=row[7] or "active",
        comment=row[8] or "",
    )
