"""Job de retención / conservación 4 años (REQ-03).

Política (Reglas de Oro #1/#4 + skill rgpd-dataguard §6):
- NINGÚN registro con antigüedad < 4 años es elegible para borrado: el job lo rechaza.
- Los registros que cruzan los 4 años quedan marcados como 'eligible' y registrados en
  `retention_log` (la prueba de que el ciclo de conservación se siguió).
- El borrado FÍSICO de `time_record` está fuera de alcance: lo bloquea su trigger
  anti-mutación (inmutabilidad). Este job NO borra; solo guarda y registra.

Ejecutable como cron:

    python -m app.jobs.retention
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models import RetentionLog, TimeRecord
from app.db.session import SessionLocal, engine

# Años de conservación obligatoria (RDL 8/2019 art. 34.9 → desarrollado en doctrina/Inspección).
RETENTION_YEARS = 4


def retention_cutoff(now: datetime) -> datetime:
    """Frontera de retención: registros con `occurred_at` anterior a esto cruzan los 4 años."""
    return now - timedelta(days=365 * RETENTION_YEARS)


def is_retained(occurred_at: datetime, now: datetime) -> bool:
    """True si el registro DEBE conservarse aún (antigüedad < 4 años)."""
    return occurred_at >= retention_cutoff(now)


def assert_not_deletable(occurred_at: datetime, now: datetime) -> None:
    """Rechaza el borrado de un registro reciente (< 4 años) — garantía dura de REQ-03."""
    if is_retained(occurred_at, now):
        raise ValueError(
            "Borrado rechazado: el registro tiene < 4 años y debe conservarse (REQ-03)."
        )


async def run_retention(
    db: AsyncSession, *, now: datetime | None = None, execute: bool = False
) -> dict:
    """Marca como 'eligible' los `time_record` que cruzan los 4 años (sin borrar).

    `execute` se acepta para una futura fase de borrado físico, pero hoy se ignora: la
    inmutabilidad del ledger impide el DELETE. Idempotente: no duplica filas 'eligible'.
    """
    now = now or utc_now()
    cutoff = retention_cutoff(now)

    records = (
        await db.execute(
            select(TimeRecord).where(TimeRecord.occurred_at < cutoff)
        )
    ).scalars().all()

    eligible = 0
    for r in records:
        age_days = (now - r.occurred_at).days
        stmt = (
            pg_insert(RetentionLog)
            .values(
                table_name="time_record",
                record_id=r.id,
                worker_id=r.worker_id,
                occurred_at=r.occurred_at,
                age_days=age_days,
                action="eligible",
                reason=f"Antigüedad {age_days} días supera los {RETENTION_YEARS} años.",
            )
            .on_conflict_do_nothing(
                index_elements=["table_name", "record_id", "action"]
            )
        )
        result = await db.execute(stmt)
        eligible += result.rowcount or 0

    await db.commit()
    return {
        "cutoff": cutoff,
        "checked": len(records),
        "eligible": eligible,
        "retained_protected": True,
    }


async def _main() -> None:
    async with SessionLocal() as db:
        result = await run_retention(db)
    print(
        f"✅ Retención: {result['checked']} registro(s) > {RETENTION_YEARS} años, "
        f"{result['eligible']} nuevo(s) marcado(s) 'eligible'. "
        f"Ningún registro < {RETENTION_YEARS} años fue tocado."
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
