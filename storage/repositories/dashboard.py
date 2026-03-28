from __future__ import annotations

from sqlalchemy import func, select

from storage.models import EmployeeModel, PaymentBatchModel, ReviewEntryModel


class PostgresDashboardReadRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def dashboard_stats(self) -> dict:
        async with self.session_factory() as session:
            employee_total = await session.scalar(
                select(func.count(EmployeeModel.id)).where(EmployeeModel.is_active.is_(True))
            )
            pending_review_entries = await session.scalar(
                select(func.count(ReviewEntryModel.id)).where(ReviewEntryModel.status == "submitted")
            )
            pending_reviewer_batches = await session.scalar(
                select(func.count(PaymentBatchModel.id)).where(
                    PaymentBatchModel.source_type == "reviewer",
                    PaymentBatchModel.payout_mode == "immediate",
                    PaymentBatchModel.status == "pending",
                )
            )
            pending_smm_batches = await session.scalar(
                select(func.count(PaymentBatchModel.id)).where(
                    PaymentBatchModel.source_type == "smm",
                    PaymentBatchModel.payout_mode == "weekly",
                    PaymentBatchModel.status == "pending",
                )
            )
            return {
                "employee_total": int(employee_total or 0),
                "pending_review_entries": int(pending_review_entries or 0),
                "pending_reviewer_batches": int(pending_reviewer_batches or 0),
                "pending_smm_batches": int(pending_smm_batches or 0),
            }
