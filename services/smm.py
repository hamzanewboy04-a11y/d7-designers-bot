from __future__ import annotations

from d7_bot.db import Database


class SmmService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def list_assignments(self):
        rows = await self.db.list_active_smm_assignments_detailed()
        return [{"assignment": assignment, "employee": employee} for assignment, employee in rows]

    async def pending_batches(self):
        return await self.db.list_pending_smm_batches()
