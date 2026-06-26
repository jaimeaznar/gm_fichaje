"""Autenticación por código de empleado + PIN (REQ-05, 21).

- Login: resuelve por `code_norm`, verifica PIN (bcrypt), aplica lockout tras N
  fallos (PIN corto -> imprescindible), emite JWT con worker_id/role/pin_temporary.
- Cambio de PIN: obligatorio en primer login (pin_temporary) antes de poder fichar.
Cada fallo de PIN emite `audit_alert(login_failed)`; el bloqueo, `account_locked` (REQ-25).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_claims, get_db
from app.audit.alerts import record_alert
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


async def authenticate(db: AsyncSession, employee_code: str, pin: str) -> Worker:
    """Valida credenciales y devuelve el trabajador (REQ-05).

    Lógica compartida por la API JSON (`/auth/login`) y la ruta web SSR (`/login`):
    respuesta uniforme (no filtra existencia), lockout tras N fallos y rastro de auditoría
    (REQ-25). Lanza 401 (`_INVALID`) o 429 si la cuenta está bloqueada.
    """
    worker = await _get_worker_by_code(db, employee_code)

    # Respuesta uniforme para no filtrar si el código existe.
    if worker is None or not worker.is_active:
        raise _INVALID

    now = utc_now()
    if worker.locked_until is not None and worker.locked_until > now:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Cuenta bloqueada temporalmente por intentos fallidos.",
        )

    if not verify_pin(pin, worker.pin_hash):
        worker.failed_attempts += 1
        locked = worker.failed_attempts >= settings.max_failed_attempts
        if locked:
            worker.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            worker.failed_attempts = 0
        await db.commit()
        # REQ-25: deja rastro de cada fallo y, si procede, del bloqueo de la cuenta.
        await record_alert(
            db, "login_failed", "PIN incorrecto en login.", worker_id=worker.id
        )
        if locked:
            await record_alert(
                db,
                "account_locked",
                "Cuenta bloqueada por intentos fallidos.",
                worker_id=worker.id,
                severity="critical",
            )
        raise _INVALID

    # Éxito: limpia el contador de fallos.
    worker.failed_attempts = 0
    worker.locked_until = None
    await db.commit()
    return worker


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    worker = await authenticate(db, body.employee_code, body.pin)
    token = create_access_token(
        worker_id=str(worker.id), role=worker.role, pin_temporary=worker.pin_temporary
    )
    return TokenResponse(access_token=token, must_change_pin=worker.pin_temporary)


async def change_worker_pin(
    db: AsyncSession, worker_id: uuid.UUID, current_pin: str, new_pin: str
) -> Worker:
    """Cambia el PIN tras validarlo (REQ-05). Compartido por API y ruta web.

    Lanza 401 si el PIN actual no es correcto, o 422 si el nuevo es igual o trivial.
    Al guardar, deja `pin_temporary=False` (ya puede fichar).
    """
    worker = await db.get(Worker, worker_id)
    if worker is None:
        raise _INVALID

    if not verify_pin(current_pin, worker.pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="El PIN actual no es correcto."
        )

    if new_pin == current_pin:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El nuevo PIN debe ser distinto del actual.",
        )

    if is_trivial_pin(new_pin, worker.code_norm):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El nuevo PIN es demasiado predecible. Elige otro.",
        )

    worker.pin_hash = hash_pin(new_pin)
    worker.pin_temporary = False
    await db.commit()
    return worker


@router.post("/change-pin", response_model=TokenResponse)
async def change_pin(
    body: PinChange,
    claims: dict = Depends(get_current_claims),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    worker = await change_worker_pin(
        db, uuid.UUID(claims["worker_id"]), body.current_pin, body.new_pin
    )
    # Token nuevo ya sin la marca de PIN temporal.
    token = create_access_token(
        worker_id=str(worker.id), role=worker.role, pin_temporary=False
    )
    return TokenResponse(access_token=token, must_change_pin=False)
