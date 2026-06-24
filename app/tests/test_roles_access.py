"""Control de accesos por rol, incl. RLT/inspección (REQ-24). Requiere BD.

Admin da de alta roles rlt/inspeccion; inspección lee de forma global (solo lectura, REQ-17);
un empleado nunca accede a registros ajenos.
"""

from __future__ import annotations

import uuid

from app.audit.chain import append_event
from app.core.security import create_access_token
from app.services.onboarding import create_employee


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_admin_creates_oversight_roles(client, db):
    admin = await create_employee(db, "Adm", "Roles", role="admin")
    h = _auth(create_access_token(admin.id, "admin", pin_temporary=False))

    for role in ("rlt", "inspeccion"):
        r = await client.post(
            "/admin/workers",
            json={"first_name": "Nuevo", "last_name": role.upper(), "role": role},
            headers=h,
        )
        assert r.status_code == 201, r.text
        assert r.json()["role"] == role


async def test_inspeccion_reads_global(client, db):
    insp = await create_employee(db, "Ins", "Global", role="inspeccion")
    w = await create_employee(db, "Tra", "Bajador")
    await append_event(db, uuid.UUID(w.id), "check_in")
    h = _auth(create_access_token(insp.id, "inspeccion", pin_temporary=False))

    r = await client.get(f"/export/records.csv?worker_id={w.id}", headers=h)
    assert r.status_code == 200, r.text
    assert w.employee_code in r.text


async def test_employee_blocked_from_other(client, db):
    w = await create_employee(db, "Em", "Pleado")
    other = await create_employee(db, "Aje", "No")
    h = _auth(create_access_token(w.id, "empleado", pin_temporary=False))

    r = await client.get(f"/reports/overtime?worker_id={other.id}", headers=h)
    assert r.status_code == 403
