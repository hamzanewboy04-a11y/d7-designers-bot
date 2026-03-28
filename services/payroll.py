from __future__ import annotations

from typing import Any

from d7_bot.db import Database
from services.employees import EmployeeService
from services.reviewer import ReviewerService
from services.smm import SmmService


class PayrollService:
    def __init__(self, db: Database | Any) -> None:
        self.db = db
        self.employees = EmployeeService(db)
        self.reviewer = ReviewerService(db)
        self.smm = SmmService(db)

    async def dashboard_stats(self) -> dict:
        if hasattr(self.db, "dashboard_stats"):
            return await self.db.dashboard_stats()

        employees = await self.employees.list_active()
        pending_review_entries = await self.reviewer.pending_entries()
        pending_reviewer_batches = await self.reviewer.pending_batches()
        pending_smm_batches = await self.smm.pending_batches()
        return {
            "employee_total": len(employees),
            "pending_review_entries": len(pending_review_entries),
            "pending_reviewer_batches": len(pending_reviewer_batches),
            "pending_smm_batches": len(pending_smm_batches),
        }
