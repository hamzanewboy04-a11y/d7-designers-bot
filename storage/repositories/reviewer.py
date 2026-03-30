from __future__ import annotations

from sqlalchemy import func, select

from storage.models import EmployeeModel, PaymentBatchItemModel, PaymentBatchModel, ReviewEntryItemModel, ReviewEntryModel


class PostgresReviewerReadRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def pending_entries(self, limit: int = 50) -> list[dict]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    ReviewEntryModel.id,
                    ReviewEntryModel.employee_id,
                    EmployeeModel.display_name,
                    ReviewEntryModel.report_date,
                    func.coalesce(func.sum(ReviewEntryItemModel.total_usdt), 0.0),
                    func.count(ReviewEntryItemModel.id),
                )
                .join(EmployeeModel, EmployeeModel.id == ReviewEntryModel.employee_id)
                .outerjoin(ReviewEntryItemModel, ReviewEntryItemModel.review_entry_id == ReviewEntryModel.id)
                .where(ReviewEntryModel.status == "submitted")
                .group_by(
                    ReviewEntryModel.id,
                    ReviewEntryModel.employee_id,
                    EmployeeModel.display_name,
                    ReviewEntryModel.report_date,
                )
                .order_by(ReviewEntryModel.created_at.asc())
                .limit(limit)
            )
            rows = result.all()
            return [
                {
                    "review_entry_id": int(row[0]),
                    "employee_id": int(row[1]),
                    "display_name": row[2],
                    "report_date": row[3],
                    "total_usdt": float(row[4]),
                    "item_count": int(row[5]),
                }
                for row in rows
            ]

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
                    PaymentBatchModel.source_type == "reviewer",
                    PaymentBatchModel.payout_mode == "immediate",
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
