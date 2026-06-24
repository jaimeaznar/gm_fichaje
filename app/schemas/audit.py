"""Esquemas Pydantic v2 para auditoría (REQ-25): alertas y verificación de cadena."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_type: str
    worker_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    detail: str
    severity: str
    detected_at: datetime


class ChainBreak(BaseModel):
    worker_id: str
    kind: str
    seq: int | None


class ChainVerifyResponse(BaseModel):
    checked: int
    broken: list[ChainBreak]
