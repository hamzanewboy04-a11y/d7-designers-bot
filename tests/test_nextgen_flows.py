import os
import tempfile
import unittest

from d7_bot.db import Database, Designer, ReviewEntryItem


class NextGenFlowTests(unittest.IsolatedAsyncioTestCase):
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
        await self.db.upsert_designer(
            Designer(103, "revuser", "rev1", "reviewer", "TREV11111111111111111111111111111111")
        )
        await self.db.migrate()

        self.pm = await self.db.get_employee_by_telegram_id(101)
        self.smm = await self.db.get_employee_by_telegram_id(102)
        self.reviewer = await self.db.get_employee_by_telegram_id(103)

    async def asyncTearDown(self):
        try:
            os.remove(self.tmp.name)
        except FileNotFoundError:
            pass

    async def test_smm_assignment_entry_and_batch_flow(self):
        assert self.pm is not None
        assert self.smm is not None

        assignment_id = await self.db.add_smm_assignment(
            smm_employee_id=self.smm.id,
            channel_name="PeruNews",
            geo="PERU",
            daily_rate_usdt=15.0,
            active_from="2026-03-23",
        )
        self.assertGreater(assignment_id, 0)

        entry_id = await self.db.add_smm_daily_entry_v2(
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

        summary = await self.db.get_smm_weekly_summary("2026-03-23", "2026-03-29")
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["employee_id"], self.smm.id)
        self.assertEqual(summary[0]["total_usdt"], 15.0)

        created = await self.db.create_smm_weekly_batches("2026-03-23", "2026-03-29")
        self.assertEqual(len(created), 1)
        batch_id = created[0]["batch_id"]

        pending = await self.db.list_pending_smm_batches()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["batch_id"], batch_id)

        paid = await self.db.mark_smm_batch_paid(batch_id, self.pm.id)
        self.assertIsNotNone(paid)
        assert paid is not None
        self.assertEqual(paid["batch_id"], batch_id)

    async def test_reviewer_v2_verify_and_batch_flow(self):
        assert self.pm is not None
        assert self.reviewer is not None

        review_entry_id = await self.db.create_review_entry_v2(
            employee_id=self.reviewer.id,
            report_date="2026-03-27",
            items=[
                ReviewEntryItem("small", 5, 1.0, 5.0, ""),
                ReviewEntryItem("large", 2, 2.5, 5.0, "priority"),
            ],
            comment="batch test",
        )
        self.assertGreater(review_entry_id, 0)

        queue = await self.db.list_pending_review_entries()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["review_entry_id"], review_entry_id)

        verified = await self.db.verify_review_entry(review_entry_id, self.pm.id)
        self.assertIsNotNone(verified)
        assert verified is not None
        self.assertEqual(verified["status"], "verified")
        self.assertEqual(verified["total_usdt"], 10.0)

        created = await self.db.create_reviewer_payout_batches()
        self.assertEqual(len(created), 1)
        batch_id = created[0]["batch_id"]

        pending = await self.db.list_pending_reviewer_batches()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["batch_id"], batch_id)

        paid = await self.db.mark_reviewer_batch_paid(batch_id, self.pm.id)
        self.assertIsNotNone(paid)
        assert paid is not None
        self.assertEqual(paid["batch_id"], batch_id)


if __name__ == "__main__":
    unittest.main()
