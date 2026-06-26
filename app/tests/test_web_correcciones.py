"""Frontend SSR — correcciones, horas extra y desglose de tiempo efectivo (Fase 7).

Conecta a la UI lo que ya existía en el backend: crear correcciones versionadas (REQ-16),
el informe de horas extra por trabajador (REQ-08/12) y el desglose de jornada (REQ-07/09).
La seguridad real la imponen API+RLS; aquí el rol solo decide qué se muestra.
"""

from __future__ import annotations

from app.audit.chain import append_event
from app.core.security import create_access_token
from app.services.onboarding import create_employee
from app.web.session import COOKIE_NAME


async def _session(client, db, role: str):
    created = await create_employee(db, "Iris", "Sanz", role=role)
    token = create_access_token(created.id, role, pin_temporary=False)
    client.cookies.set(COOKIE_NAME, token)
    return created


async def test_empleado_forbidden_in_registros(client, db):
    await _session(client, db, "empleado")
    r = await client.get("/admin/registros", follow_redirects=False)
    assert r.status_code == 403


async def test_admin_registros_offers_correction(client, db):
    await _session(client, db, "admin")
    target = await create_employee(db, "Hugo", "Mas", role="empleado")
    await append_event(db, target.id, "check_in", modalidad="presencial", source="web")

    r = await client.get(f"/admin/registros?worker_id={target.id}")
    assert r.status_code == 200
    assert "Corregir" in r.text


async def test_admin_creates_correction(client, db):
    await _session(client, db, "admin")
    target = await create_employee(db, "Lía", "Gil", role="empleado")
    rec = await append_event(db, target.id, "check_in", modalidad="presencial", source="web")

    r = await client.post(
        "/admin/correccion",
        data={
            "record_id": str(rec.id),
            "worker_id": str(target.id),
            "field": "modalidad",
            "corrected_value": "teletrabajo",
            "reason": "Error de selección",
        },
    )
    assert r.status_code == 200
    assert "Corrección registrada" in r.text
    # El original se muestra junto a su corrección (audit-trail §3).
    assert "teletrabajo" in r.text
    assert "Error de selección" in r.text


async def test_correction_invalid_value_shows_error(client, db):
    await _session(client, db, "admin")
    target = await create_employee(db, "Noa", "Rey", role="empleado")
    rec = await append_event(db, target.id, "check_in", modalidad="presencial", source="web")

    r = await client.post(
        "/admin/correccion",
        data={
            "record_id": str(rec.id),
            "worker_id": str(target.id),
            "field": "modalidad",
            "corrected_value": "no_existe",
            "reason": "x",
        },
    )
    assert r.status_code == 200
    assert "modalidad" in r.text.lower()


async def test_oversight_can_open_horas(client, db):
    await _session(client, db, "supervisor")
    r = await client.get("/admin/horas")
    assert r.status_code == 200
    assert "Horas extra" in r.text


async def test_journey_breakdown_on_fichar(client, db):
    worker = await _session(client, db, "empleado")
    await append_event(db, worker.id, "check_in", modalidad="presencial", source="web")
    r = await client.get("/fichar")
    assert r.status_code == 200
    assert "Tiempo efectivo de hoy" in r.text
