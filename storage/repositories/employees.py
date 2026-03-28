from __future__ import annotations

from sqlalchemy import select

from d7_bot.db import Employee
from storage.models import EmployeeModel


class PostgresEmployeeReadRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def list_active(self) -> list[Employee]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(EmployeeModel)
                .where(EmployeeModel.is_active.is_(True))
                .order_by(EmployeeModel.display_name)
            )
            rows = result.scalars().all()
            return [
                Employee(
                    id=row.id,
                    telegram_id=row.telegram_id,
                    username=row.username,
                    display_name=row.display_name,
                    role=row.role,
                    wallet=row.wallet,
                    is_active=bool(row.is_active),
                )
                for row in rows
            ]

    async def role_counts(self) -> list[dict]:
        employees = await self.list_active()
        counts: dict[str, int] = {}
        for employee in employees:
            counts[employee.role] = counts.get(employee.role, 0) + 1
        return [{"role": role, "count": count} for role, count in sorted(counts.items())]
