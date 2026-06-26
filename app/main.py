"""Punto de entrada FastAPI.

En el arranque verifica la residencia de datos en la UE (REQ-23): si la región no es
UE, la app NO levanta. Monta los routers de auth, admin, fichaje, reports, corrections,
export y portal (API JSON) y el router web SSR (Fase 7) con sus estáticos vendorizados.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, corrections, export, fichaje, portal, reports
from app.api.export import OVERSIGHT_ROLES
from app.core.config import assert_eu_region
from app.web import STATIC_DIR, templates
from app.web import router as web
from app.web.session import WebForbidden, WebRedirect, web_claims


@asynccontextmanager
async def lifespan(app: FastAPI):
    # REQ-23: no servir datos personales fuera de la UE.
    assert_eu_region()
    yield


app = FastAPI(title="Fichajes Global Meats", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(fichaje.router)
app.include_router(reports.router)
app.include_router(corrections.router)
app.include_router(export.router)
app.include_router(portal.router)

# Frontend SSR (Fase 7): estáticos vendorizados + páginas HTML.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(web.router)


@app.exception_handler(WebRedirect)
async def _web_redirect_handler(request: Request, exc: WebRedirect) -> RedirectResponse:
    # Sesión ausente/caducada o PIN temporal: la web redirige (no devuelve 401 JSON).
    return RedirectResponse(exc.location, status_code=exc.status_code)


@app.exception_handler(WebForbidden)
async def _web_forbidden_handler(request: Request, exc: WebForbidden):
    # Rol insuficiente: muestra el 403 (la barrera real la imponen API + RLS).
    return templates.TemplateResponse(
        request,
        "403.html",
        {"claims": web_claims(request), "oversight_roles": OVERSIGHT_ROLES},
        status_code=403,
    )


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
