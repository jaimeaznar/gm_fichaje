"""Runner de migraciones SQL planas.

Aplica en orden los ficheros `NNNN_*.sql` de `app/db/migrations/` que aún no estén
registrados en `schema_migrations`. Sin Alembic (skill fastapi-supabase): SQL
versionado, idempotente y revisable.

Uso:
    python -m app.db.migrate
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import text

from app.db.session import engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _discover() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9]*.sql"))


async def _applied_versions(conn) -> set[str]:
    # schema_migrations puede no existir aún (primera migración la crea).
    exists = await conn.scalar(text("SELECT to_regclass('public.schema_migrations')"))
    if exists is None:
        return set()
    rows = await conn.execute(text("SELECT version FROM schema_migrations"))
    return {r[0] for r in rows}


async def run() -> list[str]:
    applied: list[str] = []
    async with engine.begin() as conn:
        done = await _applied_versions(conn)
        # asyncpg no admite varias sentencias en el protocolo preparado; ejecutamos
        # cada script con el protocolo simple a través de la conexión raw de asyncpg.
        raw = await conn.get_raw_connection()
        driver_conn = raw.driver_connection  # asyncpg.Connection (misma transacción)
        for path in _discover():
            version = path.stem  # p.ej. "0001_init"
            if version in done:
                continue
            sql = path.read_text(encoding="utf-8")
            await driver_conn.execute(sql)
            await conn.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:v) "
                     "ON CONFLICT (version) DO NOTHING"),
                {"v": version},
            )
            applied.append(version)
    return applied


async def _main() -> None:
    applied = await run()
    if applied:
        print("Migraciones aplicadas: " + ", ".join(applied))
    else:
        print("Sin migraciones pendientes.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
