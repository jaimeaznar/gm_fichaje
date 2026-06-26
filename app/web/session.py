"""Sesión de navegador para el frontend SSR (Fase 7).

El JWT viaja en una cookie **httpOnly** (no accesible a JS -> a prueba de XSS); htmx la
manda sola al ser same-origin. A diferencia de la API JSON (que devuelve 401), aquí la
falta o caducidad de sesión **redirige a /login**, y un rol insuficiente muestra el 403.
"""

from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, Request, Response

from app.core.config import settings
from app.core.security import decode_token

COOKIE_NAME = "gm_session"
# Cookie NO sensible que recuerda el código de empleado entre sesiones (nunca el PIN).
CODE_COOKIE = "gm_code"


class WebRedirect(Exception):
    """Redirección de sesión (la maneja un exception handler en main)."""

    def __init__(self, location: str, status_code: int = 303) -> None:
        self.location = location
        self.status_code = status_code


class WebForbidden(Exception):
    """Rol insuficiente para una pantalla; se renderiza el 403."""


def set_session(response: Response, token: str, *, secure: bool = True) -> None:
    """Guarda el JWT en una cookie httpOnly de caducidad corta (la del propio token).

    `secure` se ata al esquema de la petición: True bajo HTTPS (producción), False en
    HTTP local de desarrollo (si no, el navegador no reenvía la cookie y la sesión se pierde).
    """
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.jwt_expires_min * 60,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )


def remember_code(response: Response, employee_code: str, *, secure: bool = True) -> None:
    """Recuerda el código (no sensible) para precargarlo en el próximo login."""
    response.set_cookie(
        CODE_COOKIE,
        employee_code,
        max_age=60 * 60 * 24 * 90,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def web_claims(request: Request) -> dict | None:
    """Claims del JWT de la cookie, o None si falta/expira/es inválido."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return decode_token(token)
    except jwt.PyJWTError:
        return None


def require_web(request: Request) -> dict:
    """Exige sesión válida. Sin ella -> /login; con PIN temporal -> /cambiar-pin."""
    claims = web_claims(request)
    if claims is None:
        raise WebRedirect("/login")
    if claims.get("pin_temporary") and request.url.path != "/cambiar-pin":
        raise WebRedirect("/cambiar-pin")
    return claims


def require_web_role(*roles: str) -> Callable[[Request, dict], dict]:
    """Como `require_web` + comprobación de rol; si no, 403 (la API+RLS son la barrera real)."""

    def _checker(request: Request, claims: dict = Depends(require_web)) -> dict:
        if claims.get("role") not in roles:
            raise WebForbidden()
        return claims

    return _checker
