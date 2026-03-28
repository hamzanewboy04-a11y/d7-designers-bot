from __future__ import annotations

from sqlalchemy import func, select

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
                .order_by(func.lower(EmployeeModel.display_name), EmployeeModel.id)
            )
            employees = result.scalars().all()
            return [self._to_employee(model) for model in employees]

    async def role_counts(self) -> list[dict]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(EmployeeModel.role, func.count(EmployeeModel.id))
                .where(EmployeeModel.is_active.is_(True))
                .group_by(EmployeeModel.role)
                .order_by(EmployeeModel.role)
            )
            return [
                {"role": role or "", "count": int(count)}
                for role, count in result.all()
            ]

    @staticmethod
    def _to_employee(model: EmployeeModel) -> Employee:
        return Employee(
            id=int(model.id),
            telegram_id=model.telegram_id,
            username=model.username,
            display_name=model.display_name,
            role=model.role or "",
            wallet=model.wallet or "",
            is_active=bool(model.is_active),
        )
