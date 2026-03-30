from __future__ import annotations

from sqlalchemy import func, select

from storage.models import EmployeeModel, PaymentBatchModel, ReviewEntryModel, SmmAssignmentModel


class PostgresDashboardReadRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def dashboard_stats(self) -> dict:
        async with self.session_factory() as session:
            employee_total = int(
                (
                    await session.execute(
                        select(func.count()).select_from(EmployeeModel).where(EmployeeModel.is_active.is_(True))
                    )
                ).scalar_one()
            )
            pending_review_entries = int(
                (
                    await session.execute(
                        select(func.count()).select_from(ReviewEntryModel).where(ReviewEntryModel.status == "submitted")
                    )
                ).scalar_one()
            )
            pending_reviewer_batches = int(
                (
                    await session.execute(
                        select(func.count()).select_from(PaymentBatchModel).where(
                            PaymentBatchModel.source_type == "reviewer",
                            PaymentBatchModel.status == "pending",
                        )
                    )
                ).scalar_one()
            )
            pending_smm_batches = int(
                (
                    await session.execute(
                        select(func.count()).select_from(PaymentBatchModel).where(
                            PaymentBatchModel.source_type == "smm",
                            PaymentBatchModel.status == "pending",
                        )
                    )
                ).scalar_one()
            )
            active_smm_assignments = int(
                (
                    await session.execute(
                        select(func.count()).select_from(SmmAssignmentModel).where(SmmAssignmentModel.status == "active")
                    )
                ).scalar_one()
            )
            return {
                "employee_total": employee_total,
                "pending_review_entries": pending_review_entries,
                "pending_reviewer_batches": pending_reviewer_batches,
                "pending_smm_batches": pending_smm_batches,
                "active_smm_assignments": active_smm_assignments,
                "pending_legacy_payments": 0,
            }
