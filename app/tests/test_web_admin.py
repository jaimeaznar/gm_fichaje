"""Frontend SSR — panel de administración (Fase 7, REQ-04, 24). Requiere BD.

El rol decide qué se muestra: un empleado no entra en /admin (403); el admin sí. El alta
enseña el PIN inicial UNA sola vez y oversight puede exportar de cualquier trabajador.
"""

from __future__ import annotations

from app.core.security import create_access_token
from app.services.onboarding import create_employee
from app.web.session import COOKIE_NAME


async def _session(client, db, role: str):
    created = await create_employee(db, "Iris", "Sanz", role=role)
    token = create_access_token(created.id, role, pin_temporary=False)
    client.cookies.set(COOKIE_NAME, token)
    return created


async def test_empleado_forbidden_in_admin(client, db):
    await _session(client, db, "empleado")
    r = await client.get("/admin", follow_redirects=False)
    assert r.status_code == 403
    assert "no autorizado" in r.text.lower()


async def test_admin_panel_ok(client, db):
    await _session(client, db, "admin")
    r = await client.get("/admin")
    assert r.status_code == 200
    assert "Administración" in r.text


async def test_alta_shows_pin_once(client, db):
    await _session(client, db, "admin")
    r = await client.post(
        "/admin/alta",
        data={"first_name": "Hugo", "last_name": "Mas", "role": "empleado",
              "relation_type": "ordinaria", "usuaria_id": ""},
    )
    assert r.status_code == 200
    assert "PIN inicial" in r.text
    assert "Trabajador creado" in r.text


async def test_oversight_can_open_export(client, db):
    await _session(client, db, "supervisor")
    r = await client.get("/admin/export")
    assert r.status_code == 200
    assert "Trabajador" in r.text


async def test_empleado_forbidden_in_export(client, db):
    await _session(client, db, "empleado")
    r = await client.get("/admin/export", follow_redirects=False)
    assert r.status_code == 403
