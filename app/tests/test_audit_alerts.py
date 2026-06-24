"""Alertas de auditoría por login (REQ-25). Requiere BD.

Cada PIN incorrecto deja `login_failed`; alcanzado el umbral, `account_locked`. El listado
de alertas solo lo ve la supervisión/inspección.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token
from app.db.models import AuditAlert
from app.services.onboarding import create_employee


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wrong_pin(real: str) -> str:
    return "000000" if real != "000000" else "999999"


async def test_failed_login_generates_alert(client, db):
    w = await create_employee(db, "Fail", "Login")
    r = await client.post(
        "/auth/login",
        json={"employee_code": w.employee_code, "pin": _wrong_pin(w.pin)},
    )
    assert r.status_code == 401

    alerts = (
        await db.execute(
            select(AuditAlert).where(
                AuditAlert.worker_id == uuid.UUID(w.id),
                AuditAlert.alert_type == "login_failed",
            )
        )
    ).scalars().all()
    assert len(alerts) >= 1


async def test_lockout_generates_critical_alert(client, db):
    w = await create_employee(db, "Lock", "Out")
    wrong = _wrong_pin(w.pin)
    for _ in range(settings.max_failed_attempts):
        await client.post(
            "/auth/login", json={"employee_code": w.employee_code, "pin": wrong}
        )

    locked = (
        await db.execute(
            select(AuditAlert).where(
                AuditAlert.worker_id == uuid.UUID(w.id),
                AuditAlert.alert_type == "account_locked",
            )
        )
    ).scalars().all()
    assert len(locked) >= 1
    assert locked[0].severity == "critical"


async def test_list_alerts_authorization(client, db):
    admin = await create_employee(db, "Adm", "Alerts", role="admin")
    emp = await create_employee(db, "Emp", "NoAlerts")

    ha = _auth(create_access_token(admin.id, "admin", pin_temporary=False))
    r = await client.get("/admin/audit/alerts", headers=ha)
    assert r.status_code == 200

    he = _auth(create_access_token(emp.id, "empleado", pin_temporary=False))
    r = await client.get("/admin/audit/alerts", headers=he)
    assert r.status_code == 403
