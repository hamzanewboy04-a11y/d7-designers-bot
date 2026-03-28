from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StorageConfig:
    db_path: str
    database_url: str | None = None

    @property
    def backend(self) -> str:
        return "postgres" if self.database_url else "sqlite"


def build_storage_config(db_path: str, database_url: str | None) -> StorageConfig:
    return StorageConfig(db_path=db_path, database_url=database_url)
