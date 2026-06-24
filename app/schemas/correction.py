"""Esquemas Pydantic v2 para correcciones versionadas (REQ-16).

La corrección no edita el original: registra el campo, su valor corregido, el motivo
(obligatorio) y el autor. Se sella en una cadena de hash propia (ver app/audit/chain.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CorrectionCreate(BaseModel):
    field: Literal["occurred_at", "event_type", "modalidad", "travel_computes", "geo"]
    corrected_value: str = Field(min_length=1)
    reason: str = Field(min_length=3)


class CorrectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_record_id: uuid.UUID
    worker_id: uuid.UUID
    seq: int
    field: str
    corrected_value: str
    reason: str
    author_id: uuid.UUID
    occurred_at: datetime
    prev_hash: str
    hash: str
