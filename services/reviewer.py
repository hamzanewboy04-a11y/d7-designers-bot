from __future__ import annotations

from typing import Any

from d7_bot.db import Database


class ReviewerService:
    def __init__(self, db: Database | Any) -> None:
        self.db = db

    async def pending_entries(self):
        if hasattr(self.db, "pending_entries"):
            return await self.db.pending_entries(limit=50)
        return await self.db.list_pending_review_entries(limit=50)

    async def pending_batches(self):
        if hasattr(self.db, "pending_batches"):
            return await self.db.pending_batches()
        return await self.db.list_pending_reviewer_batches()
