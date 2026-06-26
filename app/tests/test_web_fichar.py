"""Frontend SSR — pantalla de fichar (Fase 7, REQ-01). Requiere BD.

El estado lo reconstruye el backend; los botones reflejan las transiciones válidas y una
transición inválida devuelve el fragmento con el mensaje 409 legible (htmx swap).
"""

from __future__ import annotations

from app.core.security import create_access_token
from app.services.onboarding import create_employee
from app.web.session import COOKIE_NAME


async def _session(client, db, role: str = "empleado"):
    created = await create_employee(db, "Eva", "Mora", role=role)
    token = create_access_token(created.id, role, pin_temporary=False)
    client.cookies.set(COOKIE_NAME, token)
    return created


async def test_fichar_idle(client, db):
    await _session(client, db)
    r = await client.get("/fichar")
    assert r.status_code == 200
    assert "Sin jornada abierta" in r.text
    assert "Entrar" in r.text


async def test_check_in_opens_journey(client, db):
    await _session(client, db)
    r = await client.post("/fichar/evento", data={"event_type": "check_in"})
    assert r.status_code == 200
    assert "Jornada abierta" in r.text
    assert "Salir" in r.text


async def test_invalid_transition_shows_message(client, db):
    await _session(client, db)
    # check_out desde IDLE no es válido: fragmento con el aviso, estado intacto.
    r = await client.post("/fichar/evento", data={"event_type": "check_out"})
    assert r.status_code == 200
    assert "inválida" in r.text.lower()
    assert "Sin jornada abierta" in r.text


async def test_full_sequence(client, db):
    await _session(client, db)
    r = await client.post("/fichar/evento", data={"event_type": "check_in"})
    assert "Jornada abierta" in r.text

    r = await client.post("/fichar/evento", data={"event_type": "break_start"})
    assert "En pausa" in r.text

    r = await client.post("/fichar/evento", data={"event_type": "break_end"})
    assert "Jornada abierta" in r.text

    r = await client.post("/fichar/evento", data={"event_type": "check_out"})
    assert "Sin jornada abierta" in r.text
