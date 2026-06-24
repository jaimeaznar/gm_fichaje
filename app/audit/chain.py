"""Servicio de escritura sellada de `time_record` (REQ-02, REQ-15).

REGLA DE ORO (skill audit-trail): ningún endpoint inserta en `time_record` sin pasar por
`append_event`. Aquí se calcula SIEMPRE el sellado (hora del servidor en UTC + hash
encadenado por trabajador), de forma serializada para evitar carreras en `prev_hash`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import chain_hash, iso8601, utc_now
from app.db.models import RecordCorrection, TimeRecord

# Semilla fija de la cadena: prev_hash del primer registro de cada trabajador.
GENESIS = "GENESIS"


def compute_record_hash(
    prev_hash: str,
    worker_id: uuid.UUID | str,
    occurred_at: datetime,
    event_type: str,
    modalidad: str,
    source: str,
    travel_computes: bool,
) -> str:
    """Hash encadenado del registro: sha256(prev_hash || payload canónico).

    El payload incluye los campos sellables en un orden fijo; cualquier alteración
    posterior rompe este hash y, en cascada, el de todos los registros siguientes.
    """
    payload = (
        f"{worker_id}|{iso8601(occurred_at)}|{event_type}|"
        f"{modalidad}|{source}|{int(travel_computes)}"
    )
    return chain_hash(prev_hash, payload)


async def append_event(
    db: AsyncSession,
    worker_id: uuid.UUID,
    event_type: str,
    *,
    modalidad: str = "presencial",
    source: str = "web",
    travel_computes: bool = True,
) -> TimeRecord:
    """Inserta un evento sellado y encadenado para `worker_id` y hace commit.

    Serializa la cadena por trabajador con un advisory lock de transacción para que dos
    inserciones concurrentes no lean el mismo `prev_hash`.
    """
    # 1) Serializa por trabajador hasta el fin de la transacción (commit/rollback).
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": str(worker_id)}
    )

    # 2) Último eslabón del trabajador -> prev_hash / seq.
    last = (
        await db.execute(
            select(TimeRecord.seq, TimeRecord.hash)
            .where(TimeRecord.worker_id == worker_id)
            .order_by(TimeRecord.seq.desc())
            .limit(1)
        )
    ).first()
    if last is None:
        prev_hash, seq = GENESIS, 1
    else:
        prev_hash, seq = last.hash, last.seq + 1

    # 3) Sella con la hora del servidor y calcula el hash.
    occurred_at = utc_now()
    record_hash = compute_record_hash(
        prev_hash, worker_id, occurred_at, event_type, modalidad, source, travel_computes
    )

    record = TimeRecord(
        worker_id=worker_id,
        seq=seq,
        event_type=event_type,
        occurred_at=occurred_at,
        modalidad=modalidad,
        source=source,
        travel_computes=travel_computes,
        prev_hash=prev_hash,
        hash=record_hash,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


def verify_records(records) -> tuple[bool, int | None]:
    """Recomputa una cadena de `time_record` ya cargada (en orden de `seq`).

    Pura (sin BD) para poder testearla con datos sintéticos. Devuelve `(True, None)` si es
    íntegra, o `(False, seq)` con el primer eslabón roto (hash recomputado distinto, o
    `prev_hash` que no concuerda con el anterior).
    """
    prev_hash = GENESIS
    for record in records:
        if record.prev_hash != prev_hash:
            return False, record.seq
        expected = compute_record_hash(
            prev_hash,
            record.worker_id,
            record.occurred_at,
            record.event_type,
            record.modalidad,
            record.source,
            record.travel_computes,
        )
        if record.hash != expected:
            return False, record.seq
        prev_hash = record.hash
    return True, None


async def verify_chain(db: AsyncSession, worker_id: uuid.UUID) -> tuple[bool, int | None]:
    """Carga y verifica la cadena de `time_record` de un trabajador. Base del verificador."""
    records = (
        await db.execute(
            select(TimeRecord)
            .where(TimeRecord.worker_id == worker_id)
            .order_by(TimeRecord.seq.asc())
        )
    ).scalars().all()
    return verify_records(records)


def compute_correction_hash(
    prev_hash: str,
    original_record_id: uuid.UUID | str,
    worker_id: uuid.UUID | str,
    occurred_at: datetime,
    field: str,
    corrected_value: str,
    reason: str,
    author_id: uuid.UUID | str,
) -> str:
    """Hash encadenado de una corrección: sha256(prev_hash || payload canónico)."""
    payload = (
        f"{original_record_id}|{worker_id}|{iso8601(occurred_at)}|{field}|"
        f"{corrected_value}|{reason}|{author_id}"
    )
    return chain_hash(prev_hash, payload)


async def append_correction(
    db: AsyncSession,
    original_record: TimeRecord,
    *,
    field: str,
    corrected_value: str,
    reason: str,
    author_id: uuid.UUID,
) -> RecordCorrection:
    """Inserta una corrección sellada y encadenada para el trabajador del registro original.

    La corrección NO toca el `time_record` original (inmutable): es una fila append-only en
    `record_correction` con su propia cadena de hash por trabajador.
    """
    worker_id = original_record.worker_id

    # Serializa la cadena de correcciones del trabajador (clave distinta de la del ledger).
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"corr:{worker_id}"}
    )

    last = (
        await db.execute(
            select(RecordCorrection.seq, RecordCorrection.hash)
            .where(RecordCorrection.worker_id == worker_id)
            .order_by(RecordCorrection.seq.desc())
            .limit(1)
        )
    ).first()
    if last is None:
        prev_hash, seq = GENESIS, 1
    else:
        prev_hash, seq = last.hash, last.seq + 1

    occurred_at = utc_now()
    correction_hash = compute_correction_hash(
        prev_hash,
        original_record.id,
        worker_id,
        occurred_at,
        field,
        corrected_value,
        reason,
        author_id,
    )

    correction = RecordCorrection(
        original_record_id=original_record.id,
        worker_id=worker_id,
        seq=seq,
        field=field,
        corrected_value=corrected_value,
        reason=reason,
        author_id=author_id,
        occurred_at=occurred_at,
        prev_hash=prev_hash,
        hash=correction_hash,
    )
    db.add(correction)
    await db.commit()
    await db.refresh(correction)
    return correction


def verify_correction_records(records) -> tuple[bool, int | None]:
    """Recomputa una cadena de `record_correction` ya cargada (pura, sin BD)."""
    prev_hash = GENESIS
    for c in records:
        if c.prev_hash != prev_hash:
            return False, c.seq
        expected = compute_correction_hash(
            prev_hash,
            c.original_record_id,
            c.worker_id,
            c.occurred_at,
            c.field,
            c.corrected_value,
            c.reason,
            c.author_id,
        )
        if c.hash != expected:
            return False, c.seq
        prev_hash = c.hash
    return True, None


async def verify_correction_chain(
    db: AsyncSession, worker_id: uuid.UUID
) -> tuple[bool, int | None]:
    """Carga y verifica la cadena de `record_correction` de un trabajador."""
    records = (
        await db.execute(
            select(RecordCorrection)
            .where(RecordCorrection.worker_id == worker_id)
            .order_by(RecordCorrection.seq.asc())
        )
    ).scalars().all()
    return verify_correction_records(records)
