"""Verificador de cadena de hash (REQ-25): detección de rotura + verify_all sobre BD."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.audit.chain import GENESIS, append_event, compute_record_hash, verify_records
from app.audit.verify import verify_all
from app.db.models import AuditAlert
from app.services.onboarding import create_employee


@dataclass
class _Rec:
    worker_id: uuid.UUID
    seq: int
    event_type: str
    occurred_at: datetime
    modalidad: str
    source: str
    travel_computes: bool
    prev_hash: str
    hash: str


def _chain(wid: uuid.UUID) -> list[_Rec]:
    t = datetime(2026, 6, 24, 9, 0, tzinfo=UTC)
    h1 = compute_record_hash(GENESIS, wid, t, "check_in", "presencial", "web", True)
    r1 = _Rec(wid, 1, "check_in", t, "presencial", "web", True, GENESIS, h1)
    h2 = compute_record_hash(h1, wid, t, "check_out", "presencial", "web", True)
    r2 = _Rec(wid, 2, "check_out", t, "presencial", "web", True, h1, h2)
    return [r1, r2]


def test_verify_records_intact():
    assert verify_records(_chain(uuid.uuid4())) == (True, None)


def test_verify_records_detects_tampered_hash():
    recs = _chain(uuid.uuid4())
    recs[1].hash = "tampered"
    assert verify_records(recs) == (False, 2)


def test_verify_records_detects_broken_prev_link():
    recs = _chain(uuid.uuid4())
    recs[1].prev_hash = "wrong"
    assert verify_records(recs) == (False, 2)


async def test_verify_all_intact_chain_no_alerts(client, db):
    w = await create_employee(db, "Ver", "Ify")
    await append_event(db, uuid.UUID(w.id), "check_in")
    await append_event(db, uuid.UUID(w.id), "check_out")

    result = await verify_all(db)
    assert result["checked"] >= 1
    assert result["broken"] == []

    alerts = (
        await db.execute(select(AuditAlert).where(AuditAlert.alert_type == "chain_broken"))
    ).scalars().all()
    assert alerts == []
