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
        active_smm_assignments = 0
        pending_legacy_payments = 0
        if hasattr(self.db, "list_assignments"):
            active_smm_assignments = len(await self.db.list_assignments())
        elif hasattr(self.db, "list_active_smm_assignments_detailed"):
            active_smm_assignments = len(await self.db.list_active_smm_assignments_detailed())
        if hasattr(self.db, "get_pending_payments"):
            pending_legacy_payments = len(await self.db.get_pending_payments())
        return {
            "employee_total": len(employees),
            "pending_review_entries": len(pending_review_entries),
            "pending_reviewer_batches": len(pending_reviewer_batches),
            "pending_smm_batches": len(pending_smm_batches),
            "active_smm_assignments": active_smm_assignments,
            "pending_legacy_payments": pending_legacy_payments,
        }
