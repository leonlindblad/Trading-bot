"""Database connection and session management."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings
from src.data.models import Base

_engine = None
_session_factory = None


def get_engine(url: str | None = None):
    """Get or create the async engine."""
    global _engine
    if _engine is None:
        db_url = url or get_settings().database_url
        _engine = create_async_engine(db_url, echo=False)
    return _engine


def get_session_factory(engine=None) -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        engine = engine or get_engine()
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncSession:
    """Dependency for FastAPI — yields a database session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db(engine=None):
    """Create all tables."""
    engine = engine or get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close the engine connection pool."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
