"""Punto de entrada FastAPI.

En el arranque verifica la residencia de datos en la UE (REQ-23): si la región no es
UE, la app NO levanta. Monta los routers de auth y admin.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import admin, auth
from app.core.config import assert_eu_region


@asynccontextmanager
async def lifespan(app: FastAPI):
    # REQ-23: no servir datos personales fuera de la UE.
    assert_eu_region()
    yield


app = FastAPI(title="Fichajes Global Meats", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(admin.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
