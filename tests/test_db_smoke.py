import os
import tempfile
import unittest

from d7_bot.db import Database, Designer, TaskEntry


class DatabaseSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.tmp.close()
        self.db = Database(self.tmp.name)
        await self.db.init()

    async def asyncTearDown(self):
        try:
            os.remove(self.tmp.name)
        except FileNotFoundError:
            pass

    async def test_upsert_designer_and_fetch(self):
        designer = Designer(
            telegram_id=123,
            username="tester",
            d7_nick="nick1",
            role="designer",
            wallet="T123456789ABCDEFGHJKLMNPQRSTUVWXY1",
        )
        await self.db.upsert_designer(designer)
        loaded = await self.db.get_designer(123)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.d7_nick, "nick1")
        self.assertEqual(loaded.role, "designer")

    async def test_add_task_and_prevent_duplicate(self):
        designer = Designer(
            telegram_id=123,
            username="tester",
            d7_nick="nick1",
            role="designer",
            wallet="T123456789ABCDEFGHJKLMNPQRSTUVWXY1",
        )
        await self.db.upsert_designer(designer)

        task = TaskEntry(
            designer_id=123,
            report_date="2026-03-27",
            task_code="OTHER-1001",
            cost_usdt=10.0,
            task_prefix="OTHER",
            task_group="geo",
            task_geo="OTHER",
        )

        added_first = await self.db.add_task(task)
        added_second = await self.db.add_task(task)

        self.assertTrue(added_first)
        self.assertFalse(added_second)

    async def test_list_designers_by_role(self):
        await self.db.upsert_designer(
            Designer(1, "u1", "nick1", "designer", "T123456789ABCDEFGHJKLMNPQRSTUVWXY1")
        )
        await self.db.upsert_designer(
            Designer(2, "u2", "nick2", "reviewer", "T123456789ABCDEFGHJKLMNPQRSTUVWXY2")
        )

        designers = await self.db.list_designers_by_role("designer")
        self.assertEqual(len(designers), 1)
        self.assertEqual(designers[0].telegram_id, 1)


if __name__ == "__main__":
    unittest.main()
