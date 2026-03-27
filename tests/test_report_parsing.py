import unittest

from d7_bot.handlers.report import ParsedTask, parse_task_line


class ParseTaskLineTests(unittest.TestCase):
    def test_accepts_geo_task(self):
        result = parse_task_line("PERU1-1234 12.5")
        self.assertIsInstance(result, ParsedTask)
        assert isinstance(result, ParsedTask)
        self.assertEqual(result.task_code, "PERU1-1234")
        self.assertEqual(result.cost_usdt, 12.5)
        self.assertEqual(result.task_prefix, "PERU1")
        self.assertEqual(result.task_group, "geo")
        self.assertEqual(result.task_geo, "PERU1")

    def test_accepts_visual_task(self):
        result = parse_task_line("V-77 5")
        self.assertIsInstance(result, ParsedTask)
        assert isinstance(result, ParsedTask)
        self.assertEqual(result.task_group, "visual")
        self.assertEqual(result.task_geo, "")

    def test_rejects_unknown_prefix(self):
        result = parse_task_line("PERUU-123 10")
        self.assertIsInstance(result, str)
        assert isinstance(result, str)
        self.assertIn("неизвестный префикс", result)

    def test_rejects_invalid_cost(self):
        result = parse_task_line("OTHER-123 abc")
        self.assertIsInstance(result, str)
        assert isinstance(result, str)
        self.assertIn("некорректная стоимость", result)

    def test_rejects_invalid_format(self):
        result = parse_task_line("OTHER123 10")
        self.assertIsInstance(result, str)
        assert isinstance(result, str)
        self.assertIn("неверный формат кода задачи", result)


if __name__ == "__main__":
    unittest.main()
