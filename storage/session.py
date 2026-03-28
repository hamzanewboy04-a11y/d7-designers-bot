from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from storage.engine import normalize_database_url


def create_session_factory(database_url: str):
    normalized = normalize_database_url(database_url)
    if not normalized:
        raise ValueError("DATABASE_URL is required for SQLAlchemy session factory")
    engine = create_async_engine(normalized, future=True)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
