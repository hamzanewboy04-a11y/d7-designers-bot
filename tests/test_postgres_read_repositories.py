import unittest

from storage.engine import normalize_database_url


class PostgresReadRepositoryScaffoldTests(unittest.TestCase):
    def test_normalize_database_url_postgres(self):
        raw = "postgres://user:pass@host:5432/db"
        normalized = normalize_database_url(raw)
        self.assertEqual(normalized, "postgresql+asyncpg://user:pass@host:5432/db")

    def test_normalize_database_url_postgresql(self):
        raw = "postgresql://user:pass@host:5432/db"
        normalized = normalize_database_url(raw)
        self.assertEqual(normalized, "postgresql+asyncpg://user:pass@host:5432/db")

    def test_normalize_database_url_asyncpg(self):
        raw = "postgresql+asyncpg://user:pass@host:5432/db"
        normalized = normalize_database_url(raw)
        self.assertEqual(normalized, raw)


if __name__ == "__main__":
    unittest.main()
