"""Fixtures de test.

Los tests que tocan BD usan el `DATABASE_URL` configurado (Postgres local vía
docker-compose en dev; servicio Postgres en CI). Si la BD no está disponible, esos
tests se omiten (`skip`) en lugar de fallar.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import migrate
from app.db.session import SessionLocal, engine
from app.main import app


@pytest_asyncio.fixture
async def prepared():
    """Aplica migraciones y deja la tabla worker vacía. Omite si no hay BD."""
    try:
        await migrate.run()
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE worker RESTART IDENTITY CASCADE"))
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de conexión -> skip
        pytest.skip(f"Base de datos no disponible para tests de integración: {exc}")
    yield
    # Aísla del loop del siguiente test (asyncpg liga el pool al event loop).
    await engine.dispose()


@pytest_asyncio.fixture
async def db(prepared):
    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(prepared):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
