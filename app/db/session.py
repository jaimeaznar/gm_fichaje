"""Engine y sesión async de SQLAlchemy 2.x (Supabase/Postgres vía asyncpg).

Async de punta a punta (skill fastapi-supabase). El `DATABASE_URL` es configurable
para apuntar a Postgres local (dev/tests) o al proyecto Supabase en UE.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia FastAPI: cede una sesión async y la cierra al terminar."""
    async with SessionLocal() as session:
        yield session
