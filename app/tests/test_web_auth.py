"""Frontend SSR — autenticación por cookie (Fase 7, REQ-05). Requiere BD.

Login pone el JWT en cookie httpOnly; las rutas protegidas redirigen a /login si falta y a
/cambiar-pin si el PIN es temporal; logout borra la cookie.
"""

from __future__ import annotations

import uuid

from app.api.auth import change_worker_pin
from app.core.security import create_access_token
from app.services.onboarding import create_employee
from app.web.session import COOKIE_NAME


async def test_login_page_ok(client):
    r = await client.get("/login")
    assert r.status_code == 200
    assert "Código de empleado" in r.text


async def test_login_temporary_pin_redirects_to_change(client, db):
    created = await create_employee(db, "Pepe", "Garcia")
    r = await client.post(
        "/login",
        data={"employee_code": created.employee_code, "pin": created.pin},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/cambiar-pin"
    assert r.cookies.get(COOKIE_NAME)


async def test_login_normal_pin_redirects_to_fichar(client, db):
    created = await create_employee(db, "Lola", "Lopez")
    await change_worker_pin(db, uuid.UUID(created.id), created.pin, "739104")
    r = await client.post(
        "/login",
        data={"employee_code": created.employee_code, "pin": "739104"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/fichar"
    assert r.cookies.get(COOKIE_NAME)


async def test_login_wrong_pin_shows_error(client, db):
    created = await create_employee(db, "Ana", "Ruiz")
    r = await client.post(
        "/login",
        data={"employee_code": created.employee_code, "pin": "999999"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "incorrectos" in r.text.lower()


async def test_protected_route_redirects_without_session(client):
    r = await client.get("/fichar", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


async def test_temporary_pin_redirects_to_change(client, db):
    created = await create_employee(db, "Tom", "Wood")
    token = create_access_token(created.id, "empleado", pin_temporary=True)
    client.cookies.set(COOKIE_NAME, token)
    r = await client.get("/fichar", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/cambiar-pin"


async def test_logout_clears_session(client, db):
    created = await create_employee(db, "Sam", "Diaz")
    token = create_access_token(created.id, "empleado", pin_temporary=False)
    client.cookies.set(COOKIE_NAME, token)
    r = await client.get("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    # La cabecera Set-Cookie expira la cookie de sesión.
    assert COOKIE_NAME in r.headers.get("set-cookie", "")
