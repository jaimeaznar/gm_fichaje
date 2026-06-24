"""Portal del trabajador: acceso permanente a SUS registros (REQ-18).

"Mis registros" self-service: el trabajador consulta sus propios fichajes 24/7, con detalle,
correcciones y totales del periodo (reutiliza el mismo `ExportReport` que la exportación). Aquí
NO hay parámetro `worker_id`: cada cual ve solo lo suyo. La UI HTML (Jinja2) se construye en la
fase de frontend; este endpoint es la capa de datos del portal.
"""

from __future__ import annotations

from datetime import date as date_cls

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_claims, get_db
from app.api.export import load_report
from app.schemas.export import ExportReport

router = APIRouter(prefix="/me", tags=["portal"])


@router.get("/records", response_model=ExportReport)
async def my_records(
    start: date_cls | None = None,
    end: date_cls | None = None,
    claims: dict = Depends(get_current_claims),
    db: AsyncSession = Depends(get_db),
) -> ExportReport:
    # worker_id=None → siempre el propio trabajador del JWT (self-service).
    return await load_report(db, claims, None, start, end)
