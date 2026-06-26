"""Capa de presentación (Fase 7): HTML server-rendered con Jinja2 + Alpine/htmx.

Separada de la API JSON (`app/api/*`): el frontend SOLO consume la lógica ya existente
(dominio/servicios), no reimplementa cálculo ni acceso a datos. Aquí se exponen el motor
de plantillas y las rutas de los estáticos vendorizados, compartidos por router y handlers.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.time import to_madrid

_BASE = Path(__file__).resolve().parent
TEMPLATES_DIR = str(_BASE / "templates")
STATIC_DIR = str(_BASE / "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Filtro de presentación: convierte un instante UTC a hora local de Madrid (DST automático)
# y lo formatea. Solo afecta al renderizado; el dato sellado/almacenado sigue en UTC.
templates.env.filters["madrid"] = (
    lambda dt, fmt="%d/%m/%Y %H:%M:%S": to_madrid(dt).strftime(fmt) if dt else ""
)
