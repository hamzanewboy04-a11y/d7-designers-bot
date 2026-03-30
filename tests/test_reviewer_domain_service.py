import os
import tempfile
import unittest

from d7_bot.db import Database, Designer, ReviewEntryItem
from services.reviewer_domain import ReviewerDomainService


class ReviewerDomainServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.tmp.close()
        self.db = Database(self.tmp.name)
        await self.db.init()

        await self.db.upsert_designer(
            Designer(101, "pmuser", "pm1", "project_manager", "TPM111111111111111111111111111111111")
        )
        await self.db.upsert_designer(
            Designer(103, "revuser", "rev1", "reviewer", "TREV11111111111111111111111111111111")
        )
        await self.db.migrate()

        self.pm = await self.db.get_employee_by_telegram_id(101)
        self.reviewer = await self.db.get_employee_by_telegram_id(103)
        self.service = ReviewerDomainService(self.db)

    async def asyncTearDown(self):
        try:
            os.remove(self.tmp.name)
        except FileNotFoundError:
            pass

    async def test_employee_lookup_and_admin_check_delegate(self):
        assert self.reviewer is not None
        loaded = await self.service.get_employee_by_telegram_id(103)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.id, self.reviewer.id)
        self.assertEqual(loaded.role, "reviewer")

        await self.db.add_admin(101)
        self.assertTrue(await self.service.is_admin(101, []))
        self.assertFalse(await self.service.is_admin(999999, []))

    async def test_reviewer_submission_summary_and_queue_delegate(self):
        assert self.reviewer is not None
        review_entry_id = await self.service.create_review_entry_v2(
            employee_id=self.reviewer.id,
            report_date="2026-03-27",
            items=[
                ReviewEntryItem("small", 3, 1.5, 4.5, ""),
                ReviewEntryItem("large", 1, 2.0, 2.0, "priority"),
            ],
            comment="adapter test",
        )
        self.assertGreater(review_entry_id, 0)

        summary = await self.service.get_review_entry_summary(review_entry_id)
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["status"], "submitted")
        self.assertEqual(summary["item_count"], 2)
        self.assertEqual(summary["total_usdt"], 6.5)

        queue = await self.service.list_pending_review_entries(limit=20)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["review_entry_id"], review_entry_id)

    async def test_reviewer_verify_batch_and_paid_delegate(self):
        assert self.pm is not None
        assert self.reviewer is not None

        review_entry_id = await self.service.create_review_entry_v2(
            employee_id=self.reviewer.id,
            report_date="2026-03-28",
            items=[ReviewEntryItem("small", 2, 1.0, 2.0, "")],
            comment="batch flow",
        )

        verified = await self.service.verify_review_entry(review_entry_id, self.pm.id)
        self.assertIsNotNone(verified)
        assert verified is not None
        self.assertEqual(verified["status"], "verified")

        created = await self.service.create_reviewer_payout_batches()
        self.assertEqual(len(created), 1)
        batch_id = created[0]["batch_id"]

        pending = await self.service.list_pending_reviewer_batches()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["batch_id"], batch_id)

        paid = await self.service.mark_reviewer_batch_paid(batch_id, self.pm.id)
        self.assertIsNotNone(paid)
        assert paid is not None
        self.assertEqual(paid["batch_id"], batch_id)

        history = await self.service.list_recent_reviewer_batches(limit=15)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "paid")


if __name__ == "__main__":
    unittest.main()
