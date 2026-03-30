from __future__ import annotations

from sqlalchemy import func, select

from d7_bot.db import Employee, SmmAssignment
from storage.models import EmployeeModel, PaymentBatchItemModel, PaymentBatchModel, SmmAssignmentModel


class PostgresSmmReadRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def list_assignments(self) -> list[dict]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(SmmAssignmentModel, EmployeeModel)
                .join(EmployeeModel, EmployeeModel.id == SmmAssignmentModel.smm_employee_id)
                .where(SmmAssignmentModel.status == "active", EmployeeModel.is_active.is_(True))
                .order_by(EmployeeModel.display_name.asc(), SmmAssignmentModel.channel_name.asc())
            )
            rows = result.all()
            items: list[dict] = []
            for assignment_row, employee_row in rows:
                assignment = SmmAssignment(
                    id=int(assignment_row.id),
                    smm_employee_id=int(assignment_row.smm_employee_id),
                    channel_name=assignment_row.channel_name,
                    geo=assignment_row.geo or "",
                    daily_rate_usdt=float(assignment_row.daily_rate_usdt or 0),
                    active_from=assignment_row.active_from,
                    active_to=assignment_row.active_to,
                    status=assignment_row.status or "active",
                    comment=assignment_row.comment or "",
                )
                employee = Employee(
                    id=int(employee_row.id),
                    telegram_id=employee_row.telegram_id,
                    username=employee_row.username,
                    display_name=employee_row.display_name,
                    role=employee_row.role or "",
                    wallet=employee_row.wallet or "",
                    is_active=bool(employee_row.is_active),
                )
                items.append({"assignment": assignment, "employee": employee})
            return items

    async def pending_batches(self) -> list[dict]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    PaymentBatchModel.id,
                    PaymentBatchModel.employee_id,
                    EmployeeModel.display_name,
                    PaymentBatchModel.period_start,
                    PaymentBatchModel.period_end,
                    PaymentBatchModel.total_usdt,
                    func.count(PaymentBatchItemModel.id),
                )
                .join(EmployeeModel, EmployeeModel.id == PaymentBatchModel.employee_id)
                .outerjoin(PaymentBatchItemModel, PaymentBatchItemModel.batch_id == PaymentBatchModel.id)
                .where(
                    PaymentBatchModel.source_type == "smm",
                    PaymentBatchModel.payout_mode == "weekly",
                    PaymentBatchModel.status == "pending",
                )
                .group_by(
                    PaymentBatchModel.id,
                    PaymentBatchModel.employee_id,
                    EmployeeModel.display_name,
                    PaymentBatchModel.period_start,
                    PaymentBatchModel.period_end,
                    PaymentBatchModel.total_usdt,
                    PaymentBatchModel.created_at,
                )
                .order_by(PaymentBatchModel.created_at.desc(), EmployeeModel.display_name.asc())
            )
            rows = result.all()
            return [
                {
                    "batch_id": int(row[0]),
                    "employee_id": int(row[1]),
                    "display_name": row[2],
                    "period_start": row[3],
                    "period_end": row[4],
                    "total_usdt": float(row[5]),
                    "item_count": int(row[6]),
                }
                for row in rows
            ]
