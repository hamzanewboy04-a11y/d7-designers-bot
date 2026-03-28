import os
import tempfile
import unittest

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from storage.base import Base
from storage.models import EmployeeModel, PaymentBatchModel, ReviewEntryModel
from storage.repositories.dashboard import PostgresDashboardReadRepository
from storage.repositories.employees import PostgresEmployeeReadRepository


class PostgresReadRepositoriesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.tmp.close()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.tmp.name}", future=True)
        self.session_factory = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with self.session_factory() as session:
            session.add_all(
                [
                    EmployeeModel(id=1, telegram_id=101, username="alice", display_name="Alice", role="designer", wallet="W1", is_active=True),
                    EmployeeModel(id=2, telegram_id=102, username="bob", display_name="Bob", role="reviewer", wallet="W2", is_active=True),
                    EmployeeModel(id=3, telegram_id=103, username="charlie", display_name="Charlie", role="designer", wallet="W3", is_active=False),
                ]
            )
            session.add(ReviewEntryModel(id=10, employee_id=2, report_date="2026-03-28", status="submitted"))
            session.add(ReviewEntryModel(id=11, employee_id=2, report_date="2026-03-27", status="verified"))
            session.add(
                PaymentBatchModel(
                    id=20,
                    employee_id=2,
                    payout_mode="immediate",
                    source_type="reviewer",
                    period_start="2026-03-28",
                    period_end="2026-03-28",
                    total_usdt=15,
                    status="pending",
                )
            )
            session.add(
                PaymentBatchModel(
                    id=21,
                    employee_id=1,
                    payout_mode="weekly",
                    source_type="smm",
                    period_start="2026-03-24",
                    period_end="2026-03-28",
                    total_usdt=50,
                    status="pending",
                )
            )
            session.add(
                PaymentBatchModel(
                    id=22,
                    employee_id=1,
                    payout_mode="weekly",
                    source_type="smm",
                    period_start="2026-03-17",
                    period_end="2026-03-21",
                    total_usdt=40,
                    status="paid",
                )
            )
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()
        try:
            os.remove(self.tmp.name)
        except FileNotFoundError:
            pass

    async def test_employee_repository_lists_active_and_role_counts(self):
        repo = PostgresEmployeeReadRepository(self.session_factory)

        employees = await repo.list_active()
        role_counts = await repo.role_counts()

        self.assertEqual([employee.display_name for employee in employees], ["Alice", "Bob"])
        self.assertEqual(
            role_counts,
            [
                {"role": "designer", "count": 1},
                {"role": "reviewer", "count": 1},
            ],
        )

    async def test_dashboard_repository_returns_pending_counts(self):
        repo = PostgresDashboardReadRepository(self.session_factory)

        stats = await repo.dashboard_stats()

        self.assertEqual(
            stats,
            {
                "employee_total": 2,
                "pending_review_entries": 1,
                "pending_reviewer_batches": 1,
                "pending_smm_batches": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
