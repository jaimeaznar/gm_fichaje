"""Exportación verificable PDF/CSV (REQ-04, REQ-17, REQ-19). Requiere BD.

El informe incluye identificación, detalle diario con sellado (hash), correcciones y totales.
Acceso self + oversight: inspección descarga de cualquiera; un empleado solo lo suyo.
"""

from __future__ import annotations

import uuid

from app.audit.chain import append_correction, append_event
from app.core.security import create_access_token
from app.services.onboarding import create_employee


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _events_for(db, worker_id: str) -> None:
    await append_event(db, uuid.UUID(worker_id), "check_in")
    await append_event(db, uuid.UUID(worker_id), "check_out")


async def test_export_csv_own(client, db):
    w = await create_employee(db, "Ex", "Port")
    await _events_for(db, w.id)
    h = _auth(create_access_token(w.id, "empleado", pin_temporary=False))

    r = await client.get("/export/records.csv", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    assert w.employee_code in body
    assert "efectivo_min" in body  # totales del periodo
    assert "hash" in body  # detalle sellado verificable
    assert "check_in" in body
    # Junto al UTC verificable, se añade la columna en hora local de Madrid (presentación).
    assert "occurred_at_madrid" in body


async def test_export_pdf_own(client, db):
    w = await create_employee(db, "Pe", "Defe")
    await _events_for(db, w.id)
    h = _auth(create_access_token(w.id, "empleado", pin_temporary=False))

    r = await client.get("/export/records.pdf", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


async def test_export_includes_corrections(client, db):
    admin = await create_employee(db, "Adm", "Exp", role="admin")
    w = await create_employee(db, "Con", "Corr")
    rec = await append_event(db, uuid.UUID(w.id), "check_in")
    await append_correction(
        db,
        rec,
        field="modalidad",
        corrected_value="teletrabajo",
        reason="Era teletrabajo",
        author_id=uuid.UUID(admin.id),
    )
    h = _auth(create_access_token(w.id, "empleado", pin_temporary=False))

    r = await client.get("/export/records.csv", headers=h)
    assert r.status_code == 200, r.text
    # El export muestra original + corrección, nunca solo el valor corregido.
    assert "Correcciones" in r.text
    assert "teletrabajo" in r.text
    assert "Era teletrabajo" in r.text


async def test_inspeccion_downloads_other(client, db):
    insp = await create_employee(db, "Ins", "Pec", role="inspeccion")
    w = await create_employee(db, "Aje", "No")
    await _events_for(db, w.id)
    h = _auth(create_access_token(insp.id, "inspeccion", pin_temporary=False))

    r = await client.get(f"/export/records.csv?worker_id={w.id}", headers=h)
    assert r.status_code == 200, r.text
    assert w.employee_code in r.text


async def test_employee_cannot_export_other(client, db):
    w = await create_employee(db, "Em", "Pleado")
    other = await create_employee(db, "Otro", "Worker")
    h = _auth(create_access_token(w.id, "empleado", pin_temporary=False))

    r = await client.get(f"/export/records.csv?worker_id={other.id}", headers=h)
    assert r.status_code == 403


async def test_portal_my_records(client, db):
    w = await create_employee(db, "Mis", "Registros")
    await _events_for(db, w.id)
    h = _auth(create_access_token(w.id, "empleado", pin_temporary=False))

    r = await client.get("/me/records", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["employee_code"] == w.employee_code
    assert len(body["records"]) == 2
