from __future__ import annotations

from typing import Any

from d7_bot.db import Database


class SmmService:
    def __init__(self, db: Database | Any) -> None:
        self.db = db

    async def list_assignments(self):
        if hasattr(self.db, "list_assignments"):
            return await self.db.list_assignments()
        rows = await self.db.list_active_smm_assignments_detailed()
        return [{"assignment": assignment, "employee": employee} for assignment, employee in rows]

    async def pending_batches(self):
        if hasattr(self.db, "pending_batches"):
            return await self.db.pending_batches()
        return await self.db.list_pending_smm_batches()
