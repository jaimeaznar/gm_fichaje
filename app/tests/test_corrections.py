"""Correcciones versionadas de time_record (REQ-16). Requiere BD.

Solo admin/supervisor corrigen; la corrección no toca el original y se sella en cadena.
"""

from __future__ import annotations

import uuid

from app.audit.chain import GENESIS, append_event
from app.core.security import create_access_token
from app.services.onboarding import create_employee


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _record_for(db, worker_id: str):
    return await append_event(db, uuid.UUID(worker_id), "check_in")


async def test_admin_creates_correction_chained(client, db):
    admin = await create_employee(db, "Adm", "Corr", role="admin")
    w = await create_employee(db, "Tra", "Baja")
    rec = await _record_for(db, w.id)
    h = _auth(create_access_token(admin.id, "admin", pin_temporary=False))

    payload = {
        "field": "modalidad",
        "corrected_value": "teletrabajo",
        "reason": "Error de modalidad",
    }
    r = await client.post(f"/records/{rec.id}/corrections", json=payload, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["reason"] == "Error de modalidad"
    assert body["author_id"] == admin.id
    assert body["seq"] == 1
    assert body["prev_hash"] == GENESIS

    # Segunda corrección: encadena con la primera.
    r2 = await client.post(
        f"/records/{rec.id}/corrections",
        json={"field": "geo", "corrected_value": "40.4,-3.7", "reason": "Ubicacion"},
        headers=h,
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["seq"] == 2
    assert r2.json()["prev_hash"] == body["hash"]


async def test_reason_required(client, db):
    admin = await create_employee(db, "Adm", "NoReason", role="admin")
    w = await create_employee(db, "Wk", "X")
    rec = await _record_for(db, w.id)
    h = _auth(create_access_token(admin.id, "admin", pin_temporary=False))

    r = await client.post(
        f"/records/{rec.id}/corrections",
        json={"field": "modalidad", "corrected_value": "movil", "reason": ""},
        headers=h,
    )
    assert r.status_code == 422


async def test_incoherent_value_rejected(client, db):
    admin = await create_employee(db, "Adm", "Bad", role="admin")
    w = await create_employee(db, "Wk", "Y")
    rec = await _record_for(db, w.id)
    h = _auth(create_access_token(admin.id, "admin", pin_temporary=False))

    r = await client.post(
        f"/records/{rec.id}/corrections",
        json={"field": "event_type", "corrected_value": "no_existe", "reason": "prueba"},
        headers=h,
    )
    assert r.status_code == 422


async def test_employee_cannot_correct(client, db):
    w = await create_employee(db, "Em", "Pleado")
    rec = await _record_for(db, w.id)
    h = _auth(create_access_token(w.id, "empleado", pin_temporary=False))

    r = await client.post(
        f"/records/{rec.id}/corrections",
        json={"field": "modalidad", "corrected_value": "movil", "reason": "intento"},
        headers=h,
    )
    assert r.status_code == 403


async def test_list_corrections_access(client, db):
    sup = await create_employee(db, "Sup", "Visa", role="supervisor")
    w = await create_employee(db, "Du", "Enyo")
    other = await create_employee(db, "Aje", "No")
    rec = await _record_for(db, w.id)
    hs = _auth(create_access_token(sup.id, "supervisor", pin_temporary=False))

    # Supervisor crea una corrección.
    await client.post(
        f"/records/{rec.id}/corrections",
        json={"field": "modalidad", "corrected_value": "teletrabajo", "reason": "ajuste"},
        headers=hs,
    )

    # El dueño ve sus correcciones.
    ho = _auth(create_access_token(w.id, "empleado", pin_temporary=False))
    r = await client.get(f"/records/{rec.id}/corrections", headers=ho)
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Otro empleado NO.
    hx = _auth(create_access_token(other.id, "empleado", pin_temporary=False))
    r = await client.get(f"/records/{rec.id}/corrections", headers=hx)
    assert r.status_code == 403

    # La supervisión sí.
    r = await client.get(f"/records/{rec.id}/corrections", headers=hs)
    assert r.status_code == 200
