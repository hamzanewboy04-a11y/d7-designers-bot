from __future__ import annotations

from typing import Any

from d7_bot.db import Database, Employee, ReviewEntryItem


class ReviewerDomainService:
    """Adapter layer for reviewer-domain bot flows.

    Supports two backends:
    - SQLite-oriented `d7_bot.db.Database`
    - PostgreSQL repository bundle exposing reviewer-domain methods
    """

    def __init__(self, backend: Database | Any) -> None:
        self.backend = backend

    async def get_employee_by_telegram_id(self, telegram_id: int) -> Employee | None:
        return await self.backend.get_employee_by_telegram_id(telegram_id)

    async def get_employee(self, employee_id: int) -> Employee | None:
        return await self.backend.get_employee(employee_id)

    async def list_review_rate_rules(self) -> list[dict]:
        return await self.backend.list_review_rate_rules()

    async def create_review_entry_v2(
        self,
        employee_id: int,
        report_date: str,
        items: list[ReviewEntryItem],
        comment: str = "",
    ) -> int:
        return await self.backend.create_review_entry_v2(
            employee_id=employee_id,
            report_date=report_date,
            items=items,
            comment=comment,
        )

    async def get_review_entry_summary(self, review_entry_id: int) -> dict | None:
        return await self.backend.get_review_entry_summary(review_entry_id)

    async def list_pending_review_entries(self, limit: int = 20) -> list[dict]:
        return await self.backend.list_pending_review_entries(limit=limit)

    async def verify_review_entry(self, review_entry_id: int, pm_employee_id: int) -> dict | None:
        return await self.backend.verify_review_entry(review_entry_id, pm_employee_id)

    async def reject_review_entry(self, review_entry_id: int, pm_employee_id: int, comment: str = "") -> dict | None:
        return await self.backend.reject_review_entry(review_entry_id, pm_employee_id, comment)

    async def create_reviewer_payout_batches(self) -> list[dict]:
        return await self.backend.create_reviewer_payout_batches()

    async def list_pending_reviewer_batches(self) -> list[dict]:
        return await self.backend.list_pending_reviewer_batches()

    async def mark_reviewer_batch_paid(self, batch_id: int, paid_by_employee_id: int) -> dict | None:
        return await self.backend.mark_reviewer_batch_paid(batch_id, paid_by_employee_id)

    async def list_recent_reviewer_batches(self, limit: int = 15) -> list[dict]:
        return await self.backend.list_recent_reviewer_batches(limit=limit)

    async def get_review_entry_detail(self, review_entry_id: int) -> dict | None:
        return await self.backend.get_review_entry_detail(review_entry_id)

    async def is_admin(self, telegram_id: int, config_admin_ids: list[int]) -> bool:
        return await self.backend.is_admin(telegram_id, config_admin_ids)
