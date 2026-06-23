"""Alta de empleados (skill onboarding-empleados, REQ-05).

Genera el código de empleado con reintento transaccional sobre la UNIQUE de Postgres
(la única garantía real frente a altas concurrentes), genera un PIN inicial aleatorio
no trivial, guarda solo el hash bcrypt y marca el PIN como temporal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_pin, hash_pin
from app.db.models import Worker
from app.domain.employee_code import candidate_codes


@dataclass
class CreatedWorker:
    id: str
    employee_code: str
    role: str
    pin: str  # en claro, para mostrar UNA vez
    pin_temporary: bool = True


# Tope de seguridad por si la generación de candidatos se desbocara.
_MAX_ATTEMPTS = 1000


async def create_employee(
    db: AsyncSession,
    first_name: str,
    last_name: str,
    role: str = "empleado",
    created_by: uuid.UUID | None = None,
) -> CreatedWorker:
    """Crea un trabajador. Reintenta con el siguiente código si la UNIQUE choca."""
    pin = generate_pin()
    pin_hashed = hash_pin(pin)

    last_error: IntegrityError | None = None
    for attempt, code in enumerate(candidate_codes(first_name, last_name)):
        if attempt >= _MAX_ATTEMPTS:
            break
        code_norm = code.lower()
        worker = Worker(
            code=code,
            code_norm=code_norm,
            first_name=first_name,
            last_name=last_name,
            pin_hash=pin_hashed,
            pin_temporary=True,
            role=role,
            created_by=created_by,
        )
        db.add(worker)
        try:
            await db.flush()  # fuerza el INSERT; dispara la UNIQUE si colisiona
        except IntegrityError as exc:
            last_error = exc
            await db.rollback()
            continue
        await db.commit()
        return CreatedWorker(
            id=str(worker.id),
            employee_code=worker.code,
            role=worker.role,
            pin=pin,
            pin_temporary=True,
        )

    raise RuntimeError(
        "No se pudo generar un código de empleado único tras múltiples intentos."
    ) from last_error
