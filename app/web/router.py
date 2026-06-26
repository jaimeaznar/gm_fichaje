"""Rutas web SSR (Fase 7): login, fichar, mis registros y panel admin.

Handlers FINOS: NO reimplementan cálculo ni acceso a datos. Reutilizan las mismas funciones
de dominio/servicio que la API JSON (`authenticate`, `change_worker_pin`, `append_event`,
`reconstruct_state`, `load_report`, `create_employee`, `verify_all`) — el backend es la
fuente de verdad y estas pantallas solo la reflejan. La seguridad real la imponen la API y la
RLS; aquí el rol solo decide qué se muestra (REQ-24).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as date_cls
from datetime import time as time_cls
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import authenticate, change_worker_pin
from app.api.corrections import apply_correction
from app.api.deps import get_db
from app.api.export import OVERSIGHT_ROLES, load_report
from app.api.fichaje import _alert_if_off_hours, _ordered_event_types
from app.audit.chain import append_event
from app.audit.verify import verify_all
from app.core.security import create_access_token, generate_pin, hash_pin
from app.core.time import utc_now
from app.db.models import (
    COMPUTATION_PERIODS,
    EVENT_TYPES,
    MODALIDADES,
    RELATION_TYPES,
    WORKER_ROLES,
    AuditAlert,
    TimePolicy,
    TimeRecord,
    Worker,
)
from app.domain.export import to_csv, to_pdf
from app.domain.hours import classify_overtime, journey_effective, reconstruct_journeys
from app.domain.state_machine import (
    InvalidTransition,
    State,
    next_state,
    reconstruct_state,
)
from app.services.onboarding import create_employee
from app.web import templates
from app.web.session import (
    CODE_COOKIE,
    clear_session,
    remember_code,
    require_web,
    require_web_role,
    set_session,
    web_claims,
)

# Solo admin/supervisor pueden corregir (REQ-16); rlt/inspeccion ven el informe en solo lectura.
CORRECTABLE_ROLES = {"admin", "supervisor"}
# Campos corregibles (coinciden con el validador del backend en api/corrections.py).
CORRECTABLE_FIELDS = ["occurred_at", "event_type", "modalidad", "travel_computes", "geo"]

router = APIRouter(tags=["web"], include_in_schema=False)


def _render(
    request: Request,
    name: str,
    claims: dict | None = None,
    status_code: int = 200,
    **ctx: object,
) -> HTMLResponse:
    """Renderiza una plantilla con el contexto base que necesita `base.html` (nav por rol)."""
    ctx["claims"] = claims
    ctx["oversight_roles"] = OVERSIGHT_ROLES
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _allowed_events(state: State) -> list[str]:
    """Eventos válidos desde `state`, en orden de presentación (reutiliza la máquina de estados)."""
    allowed: list[str] = []
    for ev in EVENT_TYPES:
        try:
            next_state(state, ev)
        except InvalidTransition:
            continue
        allowed.append(ev)
    return allowed


def _minutes(td: timedelta) -> int:
    return int(td.total_seconds() // 60)


def _journey_rows(journeys: list, policy: TimePolicy | None) -> list[dict]:
    """Desglosa cada jornada en bruto/pausa/desplazamiento no computable/efectivo (REQ-07/09)."""
    rows: list[dict] = []
    for j in journeys:
        bruto = (j.check_out - j.check_in) if j.check_out else None
        pausa = sum((end - start for start, end in j.pauses), timedelta(0))
        travel_no = sum(
            (end - start for start, end, computes in j.travels if not computes), timedelta(0)
        )
        rows.append(
            {
                "check_in": j.check_in,
                "check_out": j.check_out,
                "open": j.open,
                "bruto_min": _minutes(bruto) if bruto is not None else None,
                "pausa_min": _minutes(pausa),
                "travel_no_min": _minutes(travel_no),
                "efectivo_min": (
                    _minutes(journey_effective(j, policy)) if (j.check_out and policy) else None
                ),
            }
        )
    return rows


async def _estado_ctx(db: AsyncSession, worker_id: uuid.UUID) -> dict:
    """Estado de jornada + botones válidos + eventos y jornadas de hoy (mismo camino que la API)."""
    state = reconstruct_state(await _ordered_event_types(db, worker_id))

    day_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    events = (
        await db.execute(
            select(TimeRecord)
            .where(TimeRecord.worker_id == worker_id, TimeRecord.occurred_at >= day_start)
            .order_by(TimeRecord.seq.asc())
        )
    ).scalars().all()
    policy = await db.get(TimePolicy, 1)
    journeys = _journey_rows(reconstruct_journeys(list(events)), policy)

    since = None
    if state is not State.IDLE:
        check_in = (
            await db.execute(
                select(TimeRecord)
                .where(TimeRecord.worker_id == worker_id, TimeRecord.event_type == "check_in")
                .order_by(TimeRecord.seq.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if check_in is not None:
            since = check_in.occurred_at.isoformat()

    return {
        "state": state.value,
        "allowed": _allowed_events(state),
        "events": list(events),
        "journeys": journeys,
        "since": since,
    }


# --- Raíz / autenticación -------------------------------------------------------------


@router.get("/")
async def root(request: Request) -> Response:
    return RedirectResponse("/fichar" if web_claims(request) else "/login", status_code=303)


@router.get("/login")
async def login_form(request: Request) -> Response:
    if web_claims(request) is not None:
        return RedirectResponse("/fichar", status_code=303)
    return _render(request, "login.html", remembered_code=request.cookies.get(CODE_COOKIE))


@router.post("/login")
async def login_submit(
    request: Request,
    employee_code: str = Form(...),
    pin: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        worker = await authenticate(db, employee_code, pin)
    except HTTPException as exc:
        return _render(
            request,
            "login.html",
            status_code=exc.status_code,
            error=exc.detail,
            remembered_code=employee_code,
        )

    token = create_access_token(
        worker_id=str(worker.id), role=worker.role, pin_temporary=worker.pin_temporary
    )
    dest = "/cambiar-pin" if worker.pin_temporary else "/fichar"
    response = RedirectResponse(dest, status_code=303)
    secure = request.url.scheme == "https"
    set_session(response, token, secure=secure)
    remember_code(response, worker.code, secure=secure)
    return response


@router.get("/cambiar-pin")
async def change_pin_form(request: Request, claims: dict = Depends(require_web)) -> Response:
    return _render(request, "change_pin.html", claims=claims, forced=claims.get("pin_temporary"))


@router.post("/cambiar-pin")
async def change_pin_submit(
    request: Request,
    current_pin: str = Form(...),
    new_pin: str = Form(...),
    new_pin2: str = Form(...),
    claims: dict = Depends(require_web),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if new_pin != new_pin2:
        return _render(
            request,
            "change_pin.html",
            claims=claims,
            status_code=422,
            forced=claims.get("pin_temporary"),
            error="Los PIN nuevos no coinciden.",
        )

    try:
        worker = await change_worker_pin(
            db, uuid.UUID(claims["worker_id"]), current_pin, new_pin
        )
    except HTTPException as exc:
        return _render(
            request,
            "change_pin.html",
            claims=claims,
            status_code=exc.status_code,
            forced=claims.get("pin_temporary"),
            error=exc.detail,
        )

    token = create_access_token(worker_id=str(worker.id), role=worker.role, pin_temporary=False)
    response = RedirectResponse("/fichar", status_code=303)
    set_session(response, token, secure=request.url.scheme == "https")
    return response


@router.get("/logout")
async def logout() -> Response:
    response = RedirectResponse("/login", status_code=303)
    clear_session(response)
    return response


# --- Fichar ---------------------------------------------------------------------------


@router.get("/fichar")
async def fichar(
    request: Request,
    claims: dict = Depends(require_web),
    db: AsyncSession = Depends(get_db),
) -> Response:
    ctx = await _estado_ctx(db, uuid.UUID(claims["worker_id"]))
    return _render(request, "fichar.html", claims=claims, **ctx)


@router.get("/fichar/estado")
async def fichar_estado(
    request: Request,
    claims: dict = Depends(require_web),
    db: AsyncSession = Depends(get_db),
) -> Response:
    ctx = await _estado_ctx(db, uuid.UUID(claims["worker_id"]))
    return _render(request, "_estado.html", claims=claims, **ctx)


@router.post("/fichar/evento")
async def fichar_evento(
    request: Request,
    event_type: str = Form(...),
    claims: dict = Depends(require_web),
    db: AsyncSession = Depends(get_db),
) -> Response:
    worker_id = uuid.UUID(claims["worker_id"])

    # Valida la transición por el mismo camino que la API (máquina de estados + append_event).
    current = reconstruct_state(await _ordered_event_types(db, worker_id))
    try:
        next_state(current, event_type)
    except InvalidTransition as exc:
        ctx = await _estado_ctx(db, worker_id)
        # Fragmento con el mensaje 409 legible (htmx swap a 200 para reflejar el estado real).
        return _render(request, "_estado.html", claims=claims, error=str(exc), **ctx)

    record = await append_event(
        db, worker_id, event_type, modalidad="presencial", source="web"
    )
    await _alert_if_off_hours(db, worker_id, record.occurred_at)

    ctx = await _estado_ctx(db, worker_id)
    return _render(request, "_estado.html", claims=claims, **ctx)


# --- Mis registros (portal del trabajador) -------------------------------------------


def _qs(start: date_cls | None, end: date_cls | None) -> str:
    params = {}
    if start is not None:
        params["start"] = start.isoformat()
    if end is not None:
        params["end"] = end.isoformat()
    return ("?" + urlencode(params)) if params else ""


@router.get("/mis-registros")
async def mis_registros(
    request: Request,
    start: date_cls | None = None,
    end: date_cls | None = None,
    claims: dict = Depends(require_web),
    db: AsyncSession = Depends(get_db),
) -> Response:
    report = await load_report(db, claims, None, start, end)
    return _render(
        request,
        "mis_registros.html",
        claims=claims,
        report=report,
        start=start.isoformat() if start else "",
        end=end.isoformat() if end else "",
        qs=_qs(start, end),
    )


@router.get("/mis-registros/tabla")
async def mis_registros_tabla(
    request: Request,
    start: date_cls | None = None,
    end: date_cls | None = None,
    claims: dict = Depends(require_web),
    db: AsyncSession = Depends(get_db),
) -> Response:
    report = await load_report(db, claims, None, start, end)
    return _render(request, "_registros.html", claims=claims, report=report)


# --- Descargas (cookie-auth; reutilizan load_report + serializadores del dominio) -----
# La API JSON `/export/*` autentica por Bearer; estas rutas web autentican por la cookie de
# sesión y reutilizan exactamente la misma lógica (`load_report`, `to_csv`, `to_pdf`). El acceso
# a otro trabajador lo sigue gateando `load_report` (self vs OVERSIGHT_ROLES -> 403).


@router.get("/descargar/records.csv")
async def descargar_csv(
    worker_id: uuid.UUID | None = None,
    start: date_cls | None = None,
    end: date_cls | None = None,
    claims: dict = Depends(require_web),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    report = await load_report(db, claims, worker_id, start, end)
    filename = f"fichajes_{report.employee_code}.csv"
    return StreamingResponse(
        iter([to_csv(report)]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/descargar/records.pdf")
async def descargar_pdf(
    worker_id: uuid.UUID | None = None,
    start: date_cls | None = None,
    end: date_cls | None = None,
    claims: dict = Depends(require_web),
    db: AsyncSession = Depends(get_db),
) -> Response:
    report = await load_report(db, claims, worker_id, start, end)
    filename = f"fichajes_{report.employee_code}.pdf"
    return Response(
        content=to_pdf(report),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Administración -------------------------------------------------------------------


@router.get("/admin")
async def admin_panel(
    request: Request, claims: dict = Depends(require_web_role(*OVERSIGHT_ROLES))
) -> Response:
    return _render(request, "admin/panel.html", claims=claims)


@router.get("/admin/alta")
async def admin_alta_form(
    request: Request, claims: dict = Depends(require_web_role("admin"))
) -> Response:
    return _render(
        request, "admin/alta.html", claims=claims, roles=WORKER_ROLES, relation_types=RELATION_TYPES
    )


@router.post("/admin/alta")
async def admin_alta_submit(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    role: str = Form("empleado"),
    relation_type: str = Form("ordinaria"),
    usuaria_id: str = Form(""),
    geo_consent: bool = Form(False),
    claims: dict = Depends(require_web_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        usuaria = uuid.UUID(usuaria_id) if usuaria_id.strip() else None
    except ValueError:
        return _render(
            request,
            "admin/alta.html",
            claims=claims,
            status_code=422,
            roles=WORKER_ROLES,
            relation_types=RELATION_TYPES,
            error="El UUID de empresa usuaria no es válido.",
        )

    created = await create_employee(
        db,
        first_name=first_name,
        last_name=last_name,
        role=role,
        created_by=uuid.UUID(claims["worker_id"]),
        relation_type=relation_type,
        usuaria_id=usuaria,
        geo_consent=geo_consent,
    )
    return _render(
        request,
        "admin/alta.html",
        claims=claims,
        roles=WORKER_ROLES,
        relation_types=RELATION_TYPES,
        created=created,
    )


@router.get("/admin/politica")
async def admin_politica_form(
    request: Request,
    claims: dict = Depends(require_web_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    policy = await db.get(TimePolicy, 1)
    return _render(
        request, "admin/politica.html", claims=claims, policy=policy, periods=COMPUTATION_PERIODS
    )


@router.post("/admin/politica")
async def admin_politica_submit(
    request: Request,
    pause_computable_default: bool = Form(False),
    computation_period: str = Form(...),
    ordinary_hours_per_period: float = Form(...),
    desconexion_start: str = Form(""),
    desconexion_end: str = Form(""),
    claims: dict = Depends(require_web_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    policy = await db.get(TimePolicy, 1)
    policy.pause_computable_default = pause_computable_default
    policy.computation_period = computation_period
    policy.ordinary_hours_per_period = ordinary_hours_per_period
    policy.desconexion_start = (
        time_cls.fromisoformat(desconexion_start) if desconexion_start.strip() else None
    )
    policy.desconexion_end = (
        time_cls.fromisoformat(desconexion_end) if desconexion_end.strip() else None
    )
    policy.updated_at = utc_now()
    await db.commit()
    await db.refresh(policy)

    return _render(
        request,
        "admin/politica.html",
        claims=claims,
        policy=policy,
        periods=COMPUTATION_PERIODS,
        message="Política guardada.",
    )


async def _all_workers(db: AsyncSession) -> list[Worker]:
    return list(
        (await db.execute(select(Worker).order_by(Worker.code_norm.asc()))).scalars().all()
    )


@router.get("/admin/export")
async def admin_export_form(
    request: Request,
    claims: dict = Depends(require_web_role(*OVERSIGHT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    return _render(request, "admin/export.html", claims=claims, workers=await _all_workers(db))


@router.post("/admin/reset-pin")
async def admin_reset_pin(
    request: Request,
    worker_id: str = Form(...),
    claims: dict = Depends(require_web_role("admin", "supervisor")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    worker = await db.get(Worker, uuid.UUID(worker_id))
    reset = None
    if worker is not None:
        new_pin = generate_pin(worker.code_norm)
        worker.pin_hash = hash_pin(new_pin)
        worker.pin_temporary = True
        worker.failed_attempts = 0
        worker.locked_until = None
        await db.commit()
        reset = {"employee_code": worker.code, "pin": new_pin}

    return _render(
        request,
        "admin/export.html",
        claims=claims,
        workers=await _all_workers(db),
        reset=reset,
    )


# --- Registros de un trabajador + correcciones (REQ-16) ------------------------------


@router.get("/admin/registros")
async def admin_registros(
    request: Request,
    worker_id: uuid.UUID | None = None,
    start: date_cls | None = None,
    end: date_cls | None = None,
    claims: dict = Depends(require_web_role(*OVERSIGHT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    report = await load_report(db, claims, worker_id, start, end) if worker_id else None
    return _render(
        request,
        "admin/registros.html",
        claims=claims,
        workers=await _all_workers(db),
        report=report,
        selected=str(worker_id) if worker_id else "",
        can_correct=claims["role"] in CORRECTABLE_ROLES,
        correctable_fields=CORRECTABLE_FIELDS,
        event_types=EVENT_TYPES,
        modalidades=MODALIDADES,
    )


@router.post("/admin/correccion")
async def admin_correccion(
    request: Request,
    record_id: uuid.UUID = Form(...),
    worker_id: uuid.UUID = Form(...),
    field: str = Form(...),
    corrected_value: str = Form(...),
    reason: str = Form(...),
    claims: dict = Depends(require_web_role("admin", "supervisor")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    error = None
    message = None
    try:
        await apply_correction(
            db,
            record_id=record_id,
            field=field,
            corrected_value=corrected_value,
            reason=reason,
            author_id=uuid.UUID(claims["worker_id"]),
        )
        message = "Corrección registrada."
    except HTTPException as exc:
        await db.rollback()
        error = exc.detail

    report = await load_report(db, claims, worker_id, None, None)
    return _render(
        request,
        "_registros.html",
        claims=claims,
        report=report,
        can_correct=True,
        correctable_fields=CORRECTABLE_FIELDS,
        event_types=EVENT_TYPES,
        modalidades=MODALIDADES,
        error=error,
        message=message,
    )


# --- Horas extra por trabajador (REQ-08/12) ------------------------------------------


@router.get("/admin/horas")
async def admin_horas(
    request: Request,
    worker_id: uuid.UUID | None = None,
    date: date_cls | None = None,
    claims: dict = Depends(require_web_role(*OVERSIGHT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    report = None
    worker = None
    if worker_id is not None:
        worker = await db.get(Worker, worker_id)
        policy = await db.get(TimePolicy, 1)
        if worker is not None and policy is not None:
            records = (
                await db.execute(
                    select(TimeRecord)
                    .where(TimeRecord.worker_id == worker_id)
                    .order_by(TimeRecord.seq.asc())
                )
            ).scalars().all()
            reference = (
                datetime(date.year, date.month, date.day, tzinfo=UTC) if date else utc_now()
            )
            out = classify_overtime(
                list(records), policy, reference, relation_type=worker.relation_type
            )
            report = {
                "period": out["period"],
                "start": out["start"],
                "end": out["end"],
                "efectivo_min": _minutes(out["efectivo"]),
                "ordinarias_min": _minutes(out["ordinarias"]),
                "extra_min": _minutes(out["extra"]),
                "complementarias_min": _minutes(out["complementarias"]),
                "ordinary_min": _minutes(out["ordinary"]),
            }
    return _render(
        request,
        "admin/horas.html",
        claims=claims,
        workers=await _all_workers(db),
        report=report,
        worker=worker,
        selected=str(worker_id) if worker_id else "",
        date=date.isoformat() if date else "",
    )


@router.get("/admin/alertas")
async def admin_alertas(
    request: Request,
    claims: dict = Depends(require_web_role("admin", "supervisor", "inspeccion")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    alerts = (
        await db.execute(
            select(AuditAlert).order_by(AuditAlert.detected_at.desc()).limit(100)
        )
    ).scalars().all()
    return _render(request, "admin/alertas.html", claims=claims, alerts=list(alerts))


@router.post("/admin/verificar")
async def admin_verificar(
    request: Request,
    claims: dict = Depends(require_web_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    verify = await verify_all(db)
    alerts = (
        await db.execute(
            select(AuditAlert).order_by(AuditAlert.detected_at.desc()).limit(100)
        )
    ).scalars().all()
    return _render(
        request, "admin/alertas.html", claims=claims, alerts=list(alerts), verify=verify
    )
