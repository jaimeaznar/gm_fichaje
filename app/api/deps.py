"""Dependencias compartidas de la API: sesión, trabajador autenticado y control de rol."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_session

_bearer = HTTPBearer(auto_error=True)


async def get_db() -> AsyncSession:  # pragma: no cover - thin wrapper
    async for s in get_session():
        yield s


def get_current_claims(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """Decodifica el JWT y devuelve sus claims (worker_id, role, pin_temporary)."""
    try:
        return decode_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
        ) from exc


def require_role(*roles: str) -> Callable[[dict], Awaitable[dict] | dict]:
    """Factory de dependencia que exige que el rol del JWT esté en `roles`."""

    def _checker(claims: dict = Depends(get_current_claims)) -> dict:
        if claims.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Rol no autorizado para esta operación.",
            )
        return claims

    return _checker
