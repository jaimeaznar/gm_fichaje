"""Frontend SSR — portal del trabajador "Mis registros" (Fase 7, REQ-18). Requiere BD.

Reutiliza el mismo `load_report` que la API: el trabajador ve SOLO lo suyo, con totales y
enlaces de descarga CSV/PDF.
"""

from __future__ import annotations

from app.core.security import create_access_token
from app.services.onboarding import create_employee
from app.web.session import COOKIE_NAME


async def _session(client, db):
    created = await create_employee(db, "Noa", "Vidal")
    token = create_access_token(created.id, "empleado", pin_temporary=False)
    client.cookies.set(COOKIE_NAME, token)
    return created


async def test_portal_shows_own_identity_and_links(client, db):
    created = await _session(client, db)
    await client.post("/fichar/evento", data={"event_type": "check_in"})
    await client.post("/fichar/evento", data={"event_type": "check_out"})

    r = await client.get("/mis-registros")
    assert r.status_code == 200
    assert created.employee_code in r.text
    assert "Noa Vidal" in r.text
    assert "/descargar/records.csv" in r.text
    assert "/descargar/records.pdf" in r.text
    assert "Totales del periodo" in r.text
    # Las horas se muestran en hora local de Madrid (presentación), no en UTC.
    assert "Hora (Madrid)" in r.text
    assert "Hora (UTC)" not in r.text


async def test_portal_tabla_fragment(client, db):
    await _session(client, db)
    r = await client.get("/mis-registros/tabla")
    assert r.status_code == 200
    assert 'id="registros"' in r.text
