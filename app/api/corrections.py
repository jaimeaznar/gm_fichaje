"""Correcciones versionadas de registros de jornada (REQ-16).

Solo la supervisión (admin/supervisor) corrige; nunca se edita el `time_record` original.
Al consultar se muestran el registro original y sus correcciones (skill audit-trail §3).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_claims, get_db, require_role
from app.audit.chain import append_correction
from app.core.crypto import encrypt_geo
from app.db.models import EVENT_TYPES, MODALIDADES, RecordCorrection, TimeRecord
from app.schemas.correction import CorrectionCreate, CorrectionResponse

router = APIRouter(prefix="/records", tags=["corrections"])

OVERSIGHT_ROLES = {"supervisor", "admin", "rlt", "inspeccion"}


def _validate_corrected_value(field: str, value: str) -> None:
    """Valida que `corrected_value` sea coherente con el `field` (422 si no)."""
    if field == "event_type" and value not in EVENT_TYPES:
        _reject(f"event_type debe ser uno de {EVENT_TYPES}.")
    elif field == "modalidad" and value not in MODALIDADES:
        _reject(f"modalidad debe ser una de {MODALIDADES}.")
    elif field == "travel_computes" and value.lower() not in ("true", "false"):
        _reject("travel_computes debe ser 'true' o 'false'.")
    elif field == "occurred_at":
        try:
            datetime.fromisoformat(value)
        except ValueError:
            _reject("occurred_at debe ser una fecha/hora ISO-8601 válida.")


def _reject(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


async def apply_correction(
    db: AsyncSession,
    *,
    record_id: uuid.UUID,
    field: str,
    corrected_value: str,
    reason: str,
    author_id: uuid.UUID,
) -> RecordCorrection:
    """Aplica una corrección versionada (REQ-16). Fuente única reutilizada por API y web.

    Resuelve el registro (404), valida la coherencia del valor (422), cifra la geo en reposo
    (REQ-20/23) y la añade append-only con su cadena de hash propia (`append_correction`).
    """
    original = await db.get(TimeRecord, record_id)
    if original is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Registro no existe."
        )

    _validate_corrected_value(field, corrected_value)

    # La geo es dato personal cifrado en reposo (REQ-20/23): al corregirla, se sella y almacena
    # el CIPHERTEXT, nunca el texto plano (coherente con el cifrado del fichaje original).
    if field == "geo":
        corrected_value = encrypt_geo(corrected_value) or ""

    return await append_correction(
        db,
        original,
        field=field,
        corrected_value=corrected_value,
        reason=reason,
        author_id=author_id,
    )


@router.post(
    "/{record_id}/corrections",
    response_model=CorrectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_correction(
    record_id: uuid.UUID,
    body: CorrectionCreate,
    claims: dict = Depends(require_role("admin", "supervisor")),
    db: AsyncSession = Depends(get_db),
) -> RecordCorrection:
    return await apply_correction(
        db,
        record_id=record_id,
        field=body.field,
        corrected_value=body.corrected_value,
        reason=body.reason,
        author_id=uuid.UUID(claims["worker_id"]),
    )


@router.get("/{record_id}/corrections", response_model=list[CorrectionResponse])
async def list_corrections(
    record_id: uuid.UUID,
    claims: dict = Depends(get_current_claims),
    db: AsyncSession = Depends(get_db),
) -> list[RecordCorrection]:
    original = await db.get(TimeRecord, record_id)
    if original is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Registro no existe."
        )

    own = uuid.UUID(claims["worker_id"])
    if original.worker_id != own and claims.get("role") not in OVERSIGHT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado para ver las correcciones de este registro.",
        )

    rows = (
        await db.execute(
            select(RecordCorrection)
            .where(RecordCorrection.original_record_id == record_id)
            .order_by(RecordCorrection.seq.asc())
        )
    ).scalars().all()
    return list(rows)
