import os
import tempfile
import unittest

from d7_bot.db import Database, Designer
from services.smm_domain import SmmDomainService


class SmmDomainServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.tmp.close()
        self.db = Database(self.tmp.name)
        await self.db.init()

        await self.db.upsert_designer(
            Designer(101, "pmuser", "pm1", "project_manager", "TPM111111111111111111111111111111111")
        )
        await self.db.upsert_designer(
            Designer(102, "smmuser", "smm1", "smm", "TSMM11111111111111111111111111111111")
        )
        await self.db.migrate()

        self.pm = await self.db.get_employee_by_telegram_id(101)
        self.smm = await self.db.get_employee_by_telegram_id(102)
        self.service = SmmDomainService(self.db)

    async def asyncTearDown(self):
        try:
            os.remove(self.tmp.name)
        except FileNotFoundError:
            pass

    async def test_employee_lookup_role_listing_and_admin_delegate(self):
        assert self.smm is not None
        loaded = await self.service.get_employee_by_telegram_id(102)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.id, self.smm.id)
        self.assertEqual(loaded.role, "smm")

        smm_employees = await self.service.list_employees_by_role("smm")
        self.assertEqual(len(smm_employees), 1)
        self.assertEqual(smm_employees[0].id, self.smm.id)

        await self.db.add_admin(101)
        self.assertTrue(await self.service.is_admin(101, []))
        self.assertFalse(await self.service.is_admin(999999, []))

    async def test_assignment_and_daily_entry_delegate(self):
        assert self.pm is not None
        assert self.smm is not None

        assignment_id = await self.service.add_smm_assignment(
            smm_employee_id=self.smm.id,
            channel_name="PeruNews",
            geo="PERU",
            daily_rate_usdt=15.0,
            active_from="2026-03-23",
        )
        self.assertGreater(assignment_id, 0)

        assignments = await self.service.list_active_smm_assignments(self.smm.id)
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0].id, assignment_id)

        detailed = await self.service.list_active_smm_assignments_detailed()
        self.assertEqual(len(detailed), 1)
        self.assertEqual(detailed[0][0].id, assignment_id)
        self.assertEqual(detailed[0][1].id, self.smm.id)

        entry_id = await self.service.add_smm_daily_entry_v2(
            smm_employee_id=self.smm.id,
            entered_by_pm_id=self.pm.id,
            report_date="2026-03-24",
            assignment_id=assignment_id,
            channel_name_snapshot="PeruNews",
            geo_snapshot="PERU",
            daily_rate_snapshot=15.0,
            comment="ok",
        )
        self.assertGreater(entry_id, 0)

    async def test_weekly_summary_batch_and_paid_delegate(self):
        assert self.pm is not None
        assert self.smm is not None

        assignment_id = await self.service.add_smm_assignment(
            smm_employee_id=self.smm.id,
            channel_name="PeruNews",
            geo="PERU",
            daily_rate_usdt=15.0,
            active_from="2026-03-23",
        )
        await self.service.add_smm_daily_entry_v2(
            smm_employee_id=self.smm.id,
            entered_by_pm_id=self.pm.id,
            report_date="2026-03-24",
            assignment_id=assignment_id,
            channel_name_snapshot="PeruNews",
            geo_snapshot="PERU",
            daily_rate_snapshot=15.0,
            comment="ok",
        )

        summary = await self.service.get_smm_weekly_summary("2026-03-23", "2026-03-29")
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["employee_id"], self.smm.id)
        self.assertEqual(summary[0]["total_usdt"], 15.0)

        details = await self.service.get_smm_weekly_details(self.smm.id, "2026-03-23", "2026-03-29")
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["channel_name"], "PeruNews")

        created = await self.service.create_smm_weekly_batches("2026-03-23", "2026-03-29")
        self.assertEqual(len(created), 1)
        batch_id = created[0]["batch_id"]

        pending = await self.service.list_pending_smm_batches()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["batch_id"], batch_id)

        paid = await self.service.mark_smm_batch_paid(batch_id, self.pm.id)
        self.assertIsNotNone(paid)
        assert paid is not None
        self.assertEqual(paid["batch_id"], batch_id)

        history = await self.service.list_recent_smm_batches(limit=10)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "paid")


if __name__ == "__main__":
    unittest.main()
