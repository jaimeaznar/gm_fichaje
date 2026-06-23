"""Flujo extremo a extremo de PIN (REQ-05, 21). Requiere BD.

alta (admin) -> login con PIN temporal (must_change_pin) -> cambio -> login normal.
"""

from __future__ import annotations

from app.core.security import create_access_token
from app.services.onboarding import create_employee


async def _admin_token(db) -> str:
    admin = await create_employee(db, "Ada", "Admin", role="admin")
    return create_access_token(admin.id, "admin", pin_temporary=False)


async def test_full_pin_flow(client, db):
    admin_token = await _admin_token(db)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Alta de empleado por admin -> devuelve PIN una vez.
    r = await client.post(
        "/admin/workers",
        json={"first_name": "Pepe", "last_name": "Garcia"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    created = r.json()
    code, temp_pin = created["employee_code"], created["pin"]
    assert created["pin_temporary"] is True

    # Login con PIN temporal -> must_change_pin True.
    r = await client.post("/auth/login", json={"employee_code": code, "pin": temp_pin})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["must_change_pin"] is True
    token = body["access_token"]

    # Cambio de PIN.
    r = await client.post(
        "/auth/change-pin",
        json={"current_pin": temp_pin, "new_pin": "739104"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["must_change_pin"] is False

    # Login normal con el nuevo PIN.
    r = await client.post("/auth/login", json={"employee_code": code, "pin": "739104"})
    assert r.status_code == 200
    assert r.json()["must_change_pin"] is False


async def test_login_wrong_pin_rejected(client, db):
    admin_token = await _admin_token(db)
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = await client.post(
        "/admin/workers",
        json={"first_name": "Luis", "last_name": "Lopez"},
        headers=headers,
    )
    code = r.json()["employee_code"]

    r = await client.post("/auth/login", json={"employee_code": code, "pin": "999999"})
    assert r.status_code == 401


async def test_create_worker_requires_admin(client, db):
    # Token de empleado normal no puede dar de alta.
    emp_token = create_access_token("00000000-0000-0000-0000-000000000000", "empleado", False)
    r = await client.post(
        "/admin/workers",
        json={"first_name": "X", "last_name": "Y"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert r.status_code == 403
