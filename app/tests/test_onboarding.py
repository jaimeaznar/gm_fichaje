"""Alta de empleados: unicidad del código con reintento (REQ-05). Requiere BD."""

from __future__ import annotations

import uuid

from app.core.security import verify_pin
from app.db.models import Worker
from app.services.onboarding import create_employee


async def test_create_employee_basic(db):
    created = await create_employee(db, "Pepe", "Garcia")
    assert created.employee_code == "PeGa"
    assert created.pin_temporary is True
    assert len(created.pin) == 6

    worker = await db.get(Worker, uuid.UUID(created.id))
    assert worker is not None
    assert worker.code_norm == "pega"
    # Solo se guarda el hash; el PIN en claro verifica contra él.
    assert worker.pin_hash != created.pin
    assert verify_pin(created.pin, worker.pin_hash)


async def test_same_name_gets_unique_codes(db):
    c1 = await create_employee(db, "Pepe", "Garcia")
    c2 = await create_employee(db, "Pepe", "Garcia")
    c3 = await create_employee(db, "Pepe", "Garcia")
    codes = {c1.employee_code, c2.employee_code, c3.employee_code}
    assert len(codes) == 3  # ninguna colisión: la UNIQUE fuerza el reintento
    assert c1.employee_code == "PeGa"
