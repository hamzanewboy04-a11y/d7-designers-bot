from __future__ import annotations

from sqlalchemy import case, func, select, update

from d7_bot.db import Employee, ReviewEntryItem, utc_now_iso
from storage.models import EmployeeModel, PaymentBatchItemModel, PaymentBatchModel, ReviewEntryItemModel, ReviewEntryModel, ReviewRateRuleModel


class PostgresReviewerDomainRepository:
    def __init__(self, session_factory, admin_fallback=None) -> None:
        self.session_factory = session_factory
        self.admin_fallback = admin_fallback

    async def get_employee_by_telegram_id(self, telegram_id: int) -> Employee | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(EmployeeModel).where(EmployeeModel.telegram_id == telegram_id).limit(1)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            return Employee(
                id=int(row.id),
                telegram_id=row.telegram_id,
                username=row.username,
                display_name=row.display_name,
                role=row.role or "",
                wallet=row.wallet or "",
                is_active=bool(row.is_active),
            )

    async def get_employee(self, employee_id: int) -> Employee | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(EmployeeModel).where(EmployeeModel.id == employee_id).limit(1)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            return Employee(
                id=int(row.id),
                telegram_id=row.telegram_id,
                username=row.username,
                display_name=row.display_name,
                role=row.role or "",
                wallet=row.wallet or "",
                is_active=bool(row.is_active),
            )

    async def list_review_rate_rules(self) -> list[dict]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    ReviewRateRuleModel.review_type,
                    ReviewRateRuleModel.default_unit_price,
                    ReviewRateRuleModel.comment,
                )
                .where(ReviewRateRuleModel.is_active.is_(True))
                .order_by(ReviewRateRuleModel.review_type.asc())
            )
            rows = result.all()
            return [
                {
                    "review_type": row[0],
                    "default_unit_price": float(row[1] or 0),
                    "comment": row[2] or "",
                }
                for row in rows
            ]

    async def create_review_entry_v2(
        self,
        employee_id: int,
        report_date: str,
        items: list[ReviewEntryItem],
        comment: str = "",
    ) -> int:
        async with self.session_factory() as session:
            entry = ReviewEntryModel(
                employee_id=employee_id,
                report_date=report_date,
                status="submitted",
                comment=comment,
            )
            session.add(entry)
            await session.flush()

            for item in items:
                session.add(
                    ReviewEntryItemModel(
                        review_entry_id=entry.id,
                        review_type=item.review_type,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                        total_usdt=item.total_usdt,
                        comment=item.comment,
                    )
                )

            await session.commit()
            return int(entry.id)

    async def get_review_entry_summary(self, review_entry_id: int) -> dict | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    ReviewEntryModel.id,
                    ReviewEntryModel.employee_id,
                    EmployeeModel.display_name,
                    ReviewEntryModel.report_date,
                    ReviewEntryModel.status,
                    func.coalesce(func.sum(ReviewEntryItemModel.total_usdt), 0.0),
                    func.count(ReviewEntryItemModel.id),
                )
                .join(EmployeeModel, EmployeeModel.id == ReviewEntryModel.employee_id)
                .outerjoin(ReviewEntryItemModel, ReviewEntryItemModel.review_entry_id == ReviewEntryModel.id)
                .where(ReviewEntryModel.id == review_entry_id)
                .group_by(
                    ReviewEntryModel.id,
                    ReviewEntryModel.employee_id,
                    EmployeeModel.display_name,
                    ReviewEntryModel.report_date,
                    ReviewEntryModel.status,
                )
                .limit(1)
            )
            row = result.one_or_none()
            if not row:
                return None
            return {
                "review_entry_id": int(row[0]),
                "employee_id": int(row[1]),
                "display_name": row[2],
                "report_date": row[3],
                "status": row[4],
                "total_usdt": float(row[5]),
                "item_count": int(row[6]),
            }

    async def list_pending_review_entries(self, limit: int = 20) -> list[dict]:
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
                    ReviewEntryModel.created_at,
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

    async def verify_review_entry(self, review_entry_id: int, pm_employee_id: int) -> dict | None:
        summary = await self.get_review_entry_summary(review_entry_id)
        if not summary or summary["status"] != "submitted":
            return None
        async with self.session_factory() as session:
            await session.execute(
                update(ReviewEntryModel)
                .where(ReviewEntryModel.id == review_entry_id)
                .values(
                    status="verified",
                    verified_by_pm=pm_employee_id,
                    verified_at=utc_now_iso(),
                )
            )
            await session.commit()
        summary["status"] = "verified"
        return summary

    async def reject_review_entry(self, review_entry_id: int, pm_employee_id: int, comment: str = "") -> dict | None:
        summary = await self.get_review_entry_summary(review_entry_id)
        if not summary or summary["status"] != "submitted":
            return None
        async with self.session_factory() as session:
            values = {
                "status": "rejected",
                "verified_by_pm": pm_employee_id,
                "verified_at": utc_now_iso(),
            }
            if comment:
                values["comment"] = comment
            await session.execute(
                update(ReviewEntryModel)
                .where(ReviewEntryModel.id == review_entry_id)
                .values(**values)
            )
            await session.commit()
        summary["status"] = "rejected"
        return summary

    async def create_reviewer_payout_batches(self) -> list[dict]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    ReviewEntryModel.id,
                    ReviewEntryModel.employee_id,
                    EmployeeModel.display_name,
                    ReviewEntryModel.report_date,
                    func.coalesce(func.sum(ReviewEntryItemModel.total_usdt), 0.0),
                )
                .join(EmployeeModel, EmployeeModel.id == ReviewEntryModel.employee_id)
                .outerjoin(ReviewEntryItemModel, ReviewEntryItemModel.review_entry_id == ReviewEntryModel.id)
                .where(
                    ReviewEntryModel.status == "verified",
                    ~select(PaymentBatchItemModel.id)
                    .join(PaymentBatchModel, PaymentBatchModel.id == PaymentBatchItemModel.batch_id)
                    .where(
                        PaymentBatchItemModel.source_table == "review_entries",
                        PaymentBatchItemModel.source_entry_id == ReviewEntryModel.id,
                        PaymentBatchModel.status.in_(["pending", "paid"]),
                    )
                    .exists(),
                )
                .group_by(
                    ReviewEntryModel.id,
                    ReviewEntryModel.employee_id,
                    EmployeeModel.display_name,
                    ReviewEntryModel.report_date,
                )
                .having(func.coalesce(func.sum(ReviewEntryItemModel.total_usdt), 0.0) > 0)
                .order_by(ReviewEntryModel.report_date.asc(), EmployeeModel.display_name.asc())
            )
            rows = result.all()
            created: list[dict] = []
            for review_entry_id, employee_id, display_name, report_date, total_usdt in rows:
                batch = PaymentBatchModel(
                    employee_id=int(employee_id),
                    payout_mode="immediate",
                    source_type="reviewer",
                    period_start=report_date,
                    period_end=report_date,
                    total_usdt=float(total_usdt),
                    status="pending",
                )
                session.add(batch)
                await session.flush()
                session.add(
                    PaymentBatchItemModel(
                        batch_id=batch.id,
                        source_table="review_entries",
                        source_entry_id=int(review_entry_id),
                        amount_usdt=float(total_usdt),
                    )
                )
                created.append(
                    {
                        "batch_id": int(batch.id),
                        "employee_id": int(employee_id),
                        "display_name": display_name,
                        "report_date": report_date,
                        "total_usdt": float(total_usdt),
                        "review_entry_id": int(review_entry_id),
                    }
                )
            await session.commit()
            return created

    async def list_pending_reviewer_batches(self) -> list[dict]:
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

    async def mark_reviewer_batch_paid(self, batch_id: int, paid_by_employee_id: int) -> dict | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    PaymentBatchModel.id,
                    PaymentBatchModel.employee_id,
                    EmployeeModel.display_name,
                    PaymentBatchModel.period_start,
                    PaymentBatchModel.period_end,
                    PaymentBatchModel.total_usdt,
                    PaymentBatchModel.status,
                )
                .join(EmployeeModel, EmployeeModel.id == PaymentBatchModel.employee_id)
                .where(
                    PaymentBatchModel.id == batch_id,
                    PaymentBatchModel.source_type == "reviewer",
                    PaymentBatchModel.payout_mode == "immediate",
                )
                .limit(1)
            )
            row = result.one_or_none()
            if not row or row[6] != "pending":
                return None
            await session.execute(
                update(PaymentBatchModel)
                .where(PaymentBatchModel.id == batch_id)
                .values(status="paid", paid_at=utc_now_iso(), paid_by=paid_by_employee_id)
            )
            await session.commit()
            return {
                "batch_id": int(row[0]),
                "employee_id": int(row[1]),
                "display_name": row[2],
                "period_start": row[3],
                "period_end": row[4],
                "total_usdt": float(row[5]),
            }

    async def list_recent_reviewer_batches(self, limit: int = 15) -> list[dict]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    PaymentBatchModel.id,
                    PaymentBatchModel.employee_id,
                    EmployeeModel.display_name,
                    PaymentBatchModel.period_start,
                    PaymentBatchModel.period_end,
                    PaymentBatchModel.total_usdt,
                    PaymentBatchModel.status,
                    PaymentBatchModel.paid_at,
                    func.count(PaymentBatchItemModel.id),
                )
                .join(EmployeeModel, EmployeeModel.id == PaymentBatchModel.employee_id)
                .outerjoin(PaymentBatchItemModel, PaymentBatchItemModel.batch_id == PaymentBatchModel.id)
                .where(
                    PaymentBatchModel.source_type == "reviewer",
                    PaymentBatchModel.payout_mode == "immediate",
                )
                .group_by(
                    PaymentBatchModel.id,
                    PaymentBatchModel.employee_id,
                    EmployeeModel.display_name,
                    PaymentBatchModel.period_start,
                    PaymentBatchModel.period_end,
                    PaymentBatchModel.total_usdt,
                    PaymentBatchModel.status,
                    PaymentBatchModel.paid_at,
                    PaymentBatchModel.created_at,
                )
                .order_by(func.coalesce(PaymentBatchModel.paid_at, PaymentBatchModel.created_at).desc())
                .limit(limit)
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
                    "status": row[6],
                    "paid_at": row[7],
                    "item_count": int(row[8]),
                }
                for row in rows
            ]

    async def is_admin(self, telegram_id: int, config_admin_ids: list[int]) -> bool:
        if self.admin_fallback is not None:
            return await self.admin_fallback.is_admin(telegram_id, config_admin_ids)
        return telegram_id in config_admin_ids
