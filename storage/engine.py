from __future__ import annotations

from dataclasses import dataclass


def normalize_database_url(database_url: str | None) -> str | None:
    if not database_url:
        return None
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


@dataclass(frozen=True)
class StorageConfig:
    db_path: str
    database_url: str | None = None

    @property
    def backend(self) -> str:
        return "postgres" if self.database_url else "sqlite"

    @property
    def normalized_database_url(self) -> str | None:
        return normalize_database_url(self.database_url)


def build_storage_config(db_path: str, database_url: str | None) -> StorageConfig:
    return StorageConfig(db_path=db_path, database_url=database_url)
