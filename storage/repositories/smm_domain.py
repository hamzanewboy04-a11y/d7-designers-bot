from __future__ import annotations

from sqlalchemy import func, select, update

from d7_bot.db import Employee, SmmAssignment, utc_now_iso
from storage.models import EmployeeModel, PaymentBatchItemModel, PaymentBatchModel, SmmAssignmentModel, SmmDailyEntryModel


class PostgresSmmDomainRepository:
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

    async def list_employees_by_role(self, role: str | None):
        async with self.session_factory() as session:
            stmt = select(EmployeeModel).where(EmployeeModel.is_active.is_(True))
            if role is not None:
                stmt = stmt.where(EmployeeModel.role == role)
            stmt = stmt.order_by(EmployeeModel.display_name.asc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                Employee(
                    id=int(row.id),
                    telegram_id=row.telegram_id,
                    username=row.username,
                    display_name=row.display_name,
                    role=row.role or "",
                    wallet=row.wallet or "",
                    is_active=bool(row.is_active),
                )
                for row in rows
            ]

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
        async with self.session_factory() as session:
            assignment = SmmAssignmentModel(
                smm_employee_id=smm_employee_id,
                channel_name=channel_name,
                geo=geo,
                daily_rate_usdt=daily_rate_usdt,
                active_from=active_from,
                active_to=active_to,
                comment=comment,
                status="active",
            )
            session.add(assignment)
            await session.commit()
            return int(assignment.id)

    async def list_active_smm_assignments(self, smm_employee_id: int | None = None):
        async with self.session_factory() as session:
            stmt = select(SmmAssignmentModel).where(SmmAssignmentModel.status == "active")
            if smm_employee_id is not None:
                stmt = stmt.where(SmmAssignmentModel.smm_employee_id == smm_employee_id)
            stmt = stmt.order_by(SmmAssignmentModel.channel_name.asc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                SmmAssignment(
                    id=int(row.id),
                    smm_employee_id=int(row.smm_employee_id),
                    channel_name=row.channel_name,
                    geo=row.geo or "",
                    daily_rate_usdt=float(row.daily_rate_usdt or 0),
                    active_from=row.active_from,
                    active_to=row.active_to,
                    status=row.status or "active",
                    comment=row.comment or "",
                )
                for row in rows
            ]

    async def list_active_smm_assignments_detailed(self):
        async with self.session_factory() as session:
            result = await session.execute(
                select(SmmAssignmentModel, EmployeeModel)
                .join(EmployeeModel, EmployeeModel.id == SmmAssignmentModel.smm_employee_id)
                .where(SmmAssignmentModel.status == "active", EmployeeModel.is_active.is_(True))
                .order_by(EmployeeModel.display_name.asc(), SmmAssignmentModel.channel_name.asc())
            )
            rows = result.all()
            items = []
            for assignment_row, employee_row in rows:
                items.append(
                    (
                        SmmAssignment(
                            id=int(assignment_row.id),
                            smm_employee_id=int(assignment_row.smm_employee_id),
                            channel_name=assignment_row.channel_name,
                            geo=assignment_row.geo or "",
                            daily_rate_usdt=float(assignment_row.daily_rate_usdt or 0),
                            active_from=assignment_row.active_from,
                            active_to=assignment_row.active_to,
                            status=assignment_row.status or "active",
                            comment=assignment_row.comment or "",
                        ),
                        Employee(
                            id=int(employee_row.id),
                            telegram_id=employee_row.telegram_id,
                            username=employee_row.username,
                            display_name=employee_row.display_name,
                            role=employee_row.role or "",
                            wallet=employee_row.wallet or "",
                            is_active=bool(employee_row.is_active),
                        ),
                    )
                )
            return items

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
        async with self.session_factory() as session:
            entry = SmmDailyEntryModel(
                smm_employee_id=smm_employee_id,
                entered_by_pm_id=entered_by_pm_id,
                report_date=report_date,
                assignment_id=assignment_id,
                channel_name_snapshot=channel_name_snapshot,
                geo_snapshot=geo_snapshot,
                daily_rate_snapshot=daily_rate_snapshot,
                total_usdt=daily_rate_snapshot,
                comment=comment,
            )
            session.add(entry)
            await session.commit()
            return int(entry.id)

    async def get_smm_weekly_summary(self, period_start: str, period_end: str):
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    EmployeeModel.id,
                    EmployeeModel.display_name,
                    func.count(SmmDailyEntryModel.id),
                    func.count(func.distinct(SmmDailyEntryModel.report_date)),
                    func.coalesce(func.sum(SmmDailyEntryModel.total_usdt), 0.0),
                )
                .join(EmployeeModel, EmployeeModel.id == SmmDailyEntryModel.smm_employee_id)
                .where(SmmDailyEntryModel.report_date >= period_start, SmmDailyEntryModel.report_date <= period_end)
                .group_by(EmployeeModel.id, EmployeeModel.display_name)
                .order_by(func.coalesce(func.sum(SmmDailyEntryModel.total_usdt), 0.0).desc(), EmployeeModel.display_name.asc())
            )
            rows = result.all()
            return [
                {
                    "employee_id": int(row[0]),
                    "display_name": row[1],
                    "entry_count": int(row[2]),
                    "day_count": int(row[3]),
                    "total_usdt": float(row[4]),
                }
                for row in rows
            ]

    async def get_smm_weekly_details(self, employee_id: int, period_start: str, period_end: str):
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    SmmDailyEntryModel.report_date,
                    SmmDailyEntryModel.channel_name_snapshot,
                    SmmDailyEntryModel.geo_snapshot,
                    SmmDailyEntryModel.daily_rate_snapshot,
                    SmmDailyEntryModel.total_usdt,
                    SmmDailyEntryModel.comment,
                )
                .where(
                    SmmDailyEntryModel.smm_employee_id == employee_id,
                    SmmDailyEntryModel.report_date >= period_start,
                    SmmDailyEntryModel.report_date <= period_end,
                )
                .order_by(SmmDailyEntryModel.report_date.asc(), SmmDailyEntryModel.channel_name_snapshot.asc())
            )
            rows = result.all()
            return [
                {
                    "report_date": row[0],
                    "channel_name": row[1],
                    "geo": row[2] or "",
                    "daily_rate": float(row[3] or 0),
                    "total_usdt": float(row[4] or 0),
                    "comment": row[5] or "",
                }
                for row in rows
            ]

    async def create_smm_weekly_batches(self, period_start: str, period_end: str):
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    EmployeeModel.id,
                    EmployeeModel.display_name,
                    func.coalesce(func.sum(SmmDailyEntryModel.total_usdt), 0.0),
                )
                .join(EmployeeModel, EmployeeModel.id == SmmDailyEntryModel.smm_employee_id)
                .where(
                    SmmDailyEntryModel.report_date >= period_start,
                    SmmDailyEntryModel.report_date <= period_end,
                    ~select(PaymentBatchItemModel.id)
                    .join(PaymentBatchModel, PaymentBatchModel.id == PaymentBatchItemModel.batch_id)
                    .where(
                        PaymentBatchItemModel.source_table == "smm_daily_entries",
                        PaymentBatchItemModel.source_entry_id == SmmDailyEntryModel.id,
                        PaymentBatchModel.status.in_(["pending", "paid"]),
                    )
                    .exists(),
                )
                .group_by(EmployeeModel.id, EmployeeModel.display_name)
                .having(func.coalesce(func.sum(SmmDailyEntryModel.total_usdt), 0.0) > 0)
                .order_by(EmployeeModel.display_name.asc())
            )
            employees = result.all()
            created = []
            for employee_id, display_name, total_usdt in employees:
                batch = PaymentBatchModel(
                    employee_id=int(employee_id),
                    payout_mode="weekly",
                    source_type="smm",
                    period_start=period_start,
                    period_end=period_end,
                    total_usdt=float(total_usdt),
                    status="pending",
                )
                session.add(batch)
                await session.flush()

                item_result = await session.execute(
                    select(SmmDailyEntryModel.id, SmmDailyEntryModel.total_usdt)
                    .where(
                        SmmDailyEntryModel.smm_employee_id == employee_id,
                        SmmDailyEntryModel.report_date >= period_start,
                        SmmDailyEntryModel.report_date <= period_end,
                        ~select(PaymentBatchItemModel.id)
                        .join(PaymentBatchModel, PaymentBatchModel.id == PaymentBatchItemModel.batch_id)
                        .where(
                            PaymentBatchItemModel.source_table == "smm_daily_entries",
                            PaymentBatchItemModel.source_entry_id == SmmDailyEntryModel.id,
                            PaymentBatchModel.id != batch.id,
                            PaymentBatchModel.status.in_(["pending", "paid"]),
                        )
                        .exists(),
                    )
                )
                for entry_id, amount_usdt in item_result.all():
                    session.add(
                        PaymentBatchItemModel(
                            batch_id=batch.id,
                            source_table="smm_daily_entries",
                            source_entry_id=int(entry_id),
                            amount_usdt=float(amount_usdt or 0),
                        )
                    )

                created.append(
                    {
                        "batch_id": int(batch.id),
                        "employee_id": int(employee_id),
                        "display_name": display_name,
                        "total_usdt": float(total_usdt),
                    }
                )
            await session.commit()
            return created

    async def list_pending_smm_batches(self):
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

    async def mark_smm_batch_paid(self, batch_id: int, paid_by_employee_id: int):
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
                    PaymentBatchModel.source_type == "smm",
                    PaymentBatchModel.payout_mode == "weekly",
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

    async def list_recent_smm_batches(self, limit: int = 10):
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
                    PaymentBatchModel.source_type == "smm",
                    PaymentBatchModel.payout_mode == "weekly",
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
                .order_by(PaymentBatchModel.created_at.desc(), PaymentBatchModel.id.desc())
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
