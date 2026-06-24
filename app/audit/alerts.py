"""Alertas de auditoría (REQ-25).

Punto único de escritura en `audit_alert`. Lo alimentan: el verificador de cadena
(`app/audit/verify.py`) ante una rotura, y `app/api/auth.py` ante fallos/bloqueos de login.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditAlert


async def record_alert(
    db: AsyncSession,
    alert_type: str,
    detail: str,
    *,
    worker_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    severity: str = "warning",
) -> AuditAlert:
    """Inserta una alerta de auditoría y hace commit."""
    alert = AuditAlert(
        alert_type=alert_type,
        detail=detail,
        worker_id=worker_id,
        actor_id=actor_id,
        severity=severity,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert
