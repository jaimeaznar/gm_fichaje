"""Exportación verificable de la jornada en PDF/CSV (REQ-04 vigente, REQ-17/19 reforma).

Disponibilidad inmediata on-demand: el informe siempre está accesible. Acceso self + oversight
(`OVERSIGHT_ROLES`): el trabajador descarga SOLO lo suyo; inspección/RLT/admin, de cualquier
trabajador y de solo lectura (acceso remoto de Inspección, REQ-17; control por rol, REQ-24).
El informe incluye identificación, detalle diario, correcciones y totales (REQ-19).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_claims, get_db
from app.core.time import utc_now
from app.db.models import RecordCorrection, TimePolicy, TimeRecord, Worker
from app.domain.export import build_report, to_csv, to_pdf
from app.domain.hours import classify_overtime
from app.schemas.export import ExportReport

router = APIRouter(prefix="/export", tags=["export"])

OVERSIGHT_ROLES = {"supervisor", "admin", "rlt", "inspeccion"}


async def load_report(
    db: AsyncSession,
    claims: dict,
    worker_id: uuid.UUID | None,
    start: date_cls | None,
    end: date_cls | None,
) -> ExportReport:
    """Resuelve acceso, carga registros + correcciones + totales y arma el informe."""
    own = uuid.UUID(claims["worker_id"])
    target = worker_id or own
    if target != own and claims.get("role") not in OVERSIGHT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado para exportar los registros de otro trabajador.",
        )

    worker = await db.get(Worker, target)
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trabajador no existe.")

    policy = await db.get(TimePolicy, 1)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Política no inicializada."
        )

    query = select(TimeRecord).where(TimeRecord.worker_id == target)
    if start is not None:
        query = query.where(
            TimeRecord.occurred_at >= datetime(start.year, start.month, start.day, tzinfo=UTC)
        )
    if end is not None:
        end_dt = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1)
        query = query.where(TimeRecord.occurred_at < end_dt)
    records = (await db.execute(query.order_by(TimeRecord.seq.asc()))).scalars().all()

    corrections = (
        await db.execute(
            select(RecordCorrection)
            .where(RecordCorrection.worker_id == target)
            .order_by(RecordCorrection.seq.asc())
        )
    ).scalars().all()

    summary = classify_overtime(records, policy, utc_now())
    return build_report(worker, list(records), list(corrections), summary)


@router.get("/records.csv")
async def export_csv(
    worker_id: uuid.UUID | None = None,
    start: date_cls | None = None,
    end: date_cls | None = None,
    claims: dict = Depends(get_current_claims),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    report = await load_report(db, claims, worker_id, start, end)
    content = to_csv(report)
    filename = f"fichajes_{report.employee_code}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/records.pdf")
async def export_pdf(
    worker_id: uuid.UUID | None = None,
    start: date_cls | None = None,
    end: date_cls | None = None,
    claims: dict = Depends(get_current_claims),
    db: AsyncSession = Depends(get_db),
) -> Response:
    report = await load_report(db, claims, worker_id, start, end)
    content = to_pdf(report)
    filename = f"fichajes_{report.employee_code}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
