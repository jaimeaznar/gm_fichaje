"""Autenticación por código de empleado + PIN (REQ-05, 21).

- Login: resuelve por `code_norm`, verifica PIN (bcrypt), aplica lockout tras N
  fallos (PIN corto -> imprescindible), emite JWT con worker_id/role/pin_temporary.
- Cambio de PIN: obligatorio en primer login (pin_temporary) antes de poder fichar.
La emisión de `audit_alert` por bloqueo/fallos se cablea en Fase 4.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_claims, get_db
from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_pin,
    is_trivial_pin,
    verify_pin,
)
from app.core.time import utc_now
from app.db.models import Worker
from app.domain.employee_code import normalize
from app.schemas.worker import LoginRequest, PinChange, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Código de empleado o PIN incorrectos.",
)


async def _get_worker_by_code(db: AsyncSession, employee_code: str) -> Worker | None:
    code_norm = normalize(employee_code)
    return await db.scalar(select(Worker).where(Worker.code_norm == code_norm))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    worker = await _get_worker_by_code(db, body.employee_code)

    # Respuesta uniforme para no filtrar si el código existe.
    if worker is None or not worker.is_active:
        raise _INVALID

    now = utc_now()
    if worker.locked_until is not None and worker.locked_until > now:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Cuenta bloqueada temporalmente por intentos fallidos.",
        )

    if not verify_pin(body.pin, worker.pin_hash):
        worker.failed_attempts += 1
        if worker.failed_attempts >= settings.max_failed_attempts:
            worker.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            worker.failed_attempts = 0
        await db.commit()
        raise _INVALID

    # Éxito: limpia el contador de fallos.
    worker.failed_attempts = 0
    worker.locked_until = None
    await db.commit()

    token = create_access_token(
        worker_id=str(worker.id), role=worker.role, pin_temporary=worker.pin_temporary
    )
    return TokenResponse(access_token=token, must_change_pin=worker.pin_temporary)


@router.post("/change-pin", response_model=TokenResponse)
async def change_pin(
    body: PinChange,
    claims: dict = Depends(get_current_claims),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    worker = await db.get(Worker, uuid.UUID(claims["worker_id"]))
    if worker is None:
        raise _INVALID

    if not verify_pin(body.current_pin, worker.pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="El PIN actual no es correcto."
        )

    if body.new_pin == body.current_pin:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El nuevo PIN debe ser distinto del actual.",
        )

    if is_trivial_pin(body.new_pin, worker.code_norm):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El nuevo PIN es demasiado predecible. Elige otro.",
        )

    worker.pin_hash = hash_pin(body.new_pin)
    worker.pin_temporary = False
    await db.commit()

    # Token nuevo ya sin la marca de PIN temporal.
    token = create_access_token(
        worker_id=str(worker.id), role=worker.role, pin_temporary=False
    )
    return TokenResponse(access_token=token, must_change_pin=False)
