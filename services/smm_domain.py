from __future__ import annotations

from typing import Any

from d7_bot.db import Database, Employee


class SmmDomainService:
    def __init__(self, backend: Database | Any) -> None:
        self.backend = backend

    async def get_employee_by_telegram_id(self, telegram_id: int) -> Employee | None:
        return await self.backend.get_employee_by_telegram_id(telegram_id)

    async def get_employee(self, employee_id: int) -> Employee | None:
        return await self.backend.get_employee(employee_id)

    async def list_employees_by_role(self, role: str | None):
        return await self.backend.list_employees_by_role(role)

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
        return await self.backend.add_smm_assignment(
            smm_employee_id=smm_employee_id,
            channel_name=channel_name,
            geo=geo,
            daily_rate_usdt=daily_rate_usdt,
            active_from=active_from,
            active_to=active_to,
            comment=comment,
        )

    async def list_active_smm_assignments(self, smm_employee_id: int | None = None):
        return await self.backend.list_active_smm_assignments(smm_employee_id)

    async def list_active_smm_assignments_detailed(self):
        return await self.backend.list_active_smm_assignments_detailed()

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
        return await self.backend.add_smm_daily_entry_v2(
            smm_employee_id=smm_employee_id,
            entered_by_pm_id=entered_by_pm_id,
            report_date=report_date,
            assignment_id=assignment_id,
            channel_name_snapshot=channel_name_snapshot,
            geo_snapshot=geo_snapshot,
            daily_rate_snapshot=daily_rate_snapshot,
            comment=comment,
        )

    async def get_smm_weekly_summary(self, period_start: str, period_end: str):
        return await self.backend.get_smm_weekly_summary(period_start, period_end)

    async def get_smm_weekly_details(self, employee_id: int, period_start: str, period_end: str):
        return await self.backend.get_smm_weekly_details(employee_id, period_start, period_end)

    async def create_smm_weekly_batches(self, period_start: str, period_end: str):
        return await self.backend.create_smm_weekly_batches(period_start, period_end)

    async def list_pending_smm_batches(self):
        return await self.backend.list_pending_smm_batches()

    async def mark_smm_batch_paid(self, batch_id: int, paid_by_employee_id: int):
        return await self.backend.mark_smm_batch_paid(batch_id, paid_by_employee_id)

    async def list_recent_smm_batches(self, limit: int = 10):
        return await self.backend.list_recent_smm_batches(limit)

    async def is_admin(self, telegram_id: int, config_admin_ids: list[int]) -> bool:
        return await self.backend.is_admin(telegram_id, config_admin_ids)
