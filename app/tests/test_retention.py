"""Retención / conservación 4 años (REQ-03). Unit + integración (BD).

El job NUNCA borra registros < 4 años (los rechaza) y marca como 'eligible' los que cruzan el
umbral, registrándolos en retention_log (prueba del cumplimiento). No borra el ledger (inmutable).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.audit.chain import append_event
from app.core.time import utc_now
from app.db.models import RetentionLog
from app.jobs.retention import (
    RETENTION_YEARS,
    assert_not_deletable,
    is_retained,
    retention_cutoff,
    run_retention,
)
from app.services.onboarding import create_employee


def test_is_retained_recent_true():
    now = utc_now()
    one_year_ago = now - timedelta(days=365)
    assert is_retained(one_year_ago, now) is True


def test_is_retained_old_false():
    now = utc_now()
    over_four = now - timedelta(days=365 * RETENTION_YEARS + 1)
    assert is_retained(over_four, now) is False


def test_assert_not_deletable_rejects_recent():
    now = utc_now()
    recent = now - timedelta(days=10)
    with pytest.raises(ValueError):
        assert_not_deletable(recent, now)


def test_assert_not_deletable_allows_old():
    now = utc_now()
    old = retention_cutoff(now) - timedelta(days=1)
    assert_not_deletable(old, now)  # no lanza


async def test_run_retention_marks_eligible(db):
    w = await create_employee(db, "Ret", "Encion")
    rec = await append_event(db, uuid.UUID(w.id), "check_in")

    # `now` 5 años en el futuro: el registro cruza los 4 años -> elegible.
    future = utc_now() + timedelta(days=365 * 5)
    result = await run_retention(db, now=future)
    assert result["eligible"] >= 1
    assert result["retained_protected"] is True

    rows = (
        await db.execute(
            select(RetentionLog).where(RetentionLog.record_id == rec.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].action == "eligible"


async def test_run_retention_keeps_recent(db):
    w = await create_employee(db, "Recie", "Nte")
    rec = await append_event(db, uuid.UUID(w.id), "check_in")

    result = await run_retention(db, now=utc_now())
    assert result["eligible"] == 0

    rows = (
        await db.execute(
            select(RetentionLog).where(RetentionLog.record_id == rec.id)
        )
    ).scalars().all()
    assert rows == []
