from __future__ import annotations

from d7_bot.db import Database


class ReviewerService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def pending_entries(self):
        return await self.db.list_pending_review_entries(limit=50)

    async def pending_batches(self):
        return await self.db.list_pending_reviewer_batches()
