from __future__ import annotations

from collections import Counter
from typing import Any

from d7_bot.db import Database


class EmployeeService:
    def __init__(self, db: Database | Any) -> None:
        self.db = db

    async def list_active(self):
        if hasattr(self.db, "list_active"):
            return await self.db.list_active()
        return await self.db.list_employees_by_role(None)

    async def role_counts(self) -> list[dict]:
        if hasattr(self.db, "role_counts"):
            return await self.db.role_counts()
        employees = await self.db.list_employees_by_role(None)
        counts = Counter(employee.role for employee in employees)
        return [{"role": role, "count": count} for role, count in sorted(counts.items())]
