from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import aiosqlite


@dataclass
class Designer:
    telegram_id: int
    username: str | None
    d7_nick: str
    experience: str
    formats: list[str]
    portfolio: list[str]
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

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS designers (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    d7_nick TEXT NOT NULL,
                    experience TEXT NOT NULL,
                    formats_json TEXT NOT NULL,
                    portfolio_json TEXT NOT NULL,
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
                    FOREIGN KEY (designer_id) REFERENCES designers(telegram_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date);
                """
            )
            await db.commit()

    async def upsert_designer(self, designer: Designer) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO designers (telegram_id, username, d7_nick, experience, formats_json, portfolio_json, wallet, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username=excluded.username,
                    d7_nick=excluded.d7_nick,
                    experience=excluded.experience,
                    formats_json=excluded.formats_json,
                    portfolio_json=excluded.portfolio_json,
                    wallet=excluded.wallet,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    designer.telegram_id,
                    designer.username,
                    designer.d7_nick,
                    designer.experience,
                    json.dumps(designer.formats, ensure_ascii=False),
                    json.dumps(designer.portfolio, ensure_ascii=False),
                    designer.wallet,
                ),
            )
            await db.commit()

    async def get_designer(self, telegram_id: int) -> Designer | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT telegram_id, username, d7_nick, experience, formats_json, portfolio_json, wallet FROM designers WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return Designer(
                telegram_id=row[0],
                username=row[1],
                d7_nick=row[2],
                experience=row[3],
                formats=json.loads(row[4]),
                portfolio=json.loads(row[5]),
                wallet=row[6],
            )

    async def list_designers(self) -> list[Designer]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT telegram_id, username, d7_nick, experience, formats_json, portfolio_json, wallet FROM designers ORDER BY d7_nick"
            )
            rows = await cursor.fetchall()
            return [
                Designer(
                    telegram_id=row[0],
                    username=row[1],
                    d7_nick=row[2],
                    experience=row[3],
                    formats=json.loads(row[4]),
                    portfolio=json.loads(row[5]),
                    wallet=row[6],
                )
                for row in rows
            ]

    async def add_admin(self, telegram_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT OR IGNORE INTO admins (telegram_id) VALUES (?)", (telegram_id,))
            await db.commit()

    async def list_admins(self) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT telegram_id FROM admins")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def add_task(self, task: TaskEntry) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO reports (designer_id, report_date, task_code, cost_usdt) VALUES (?, ?, ?, ?)",
                (task.designer_id, task.report_date, task.task_code, task.cost_usdt),
            )
            await db.commit()

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
