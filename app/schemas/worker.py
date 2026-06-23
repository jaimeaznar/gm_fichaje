"""Esquemas Pydantic v2 para onboarding y autenticación."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.db.models import WORKER_ROLES

_PIN_FIELD = Field(..., pattern=r"^\d{6}$", description="PIN de 6 dígitos")


class WorkerCreate(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    role: str = Field(default="empleado")

    @field_validator("role")
    @classmethod
    def _role_valid(cls, v: str) -> str:
        if v not in WORKER_ROLES:
            raise ValueError(f"role debe ser uno de {WORKER_ROLES}")
        return v


class WorkerCreatedResponse(BaseModel):
    """Respuesta del alta. `pin` se muestra UNA sola vez (no se puede recuperar)."""

    id: str
    employee_code: str
    role: str
    pin: str = Field(..., description="PIN inicial en claro. Se muestra una única vez.")
    pin_temporary: bool = True


class LoginRequest(BaseModel):
    employee_code: str = Field(..., min_length=1)
    pin: str = _PIN_FIELD


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_pin: bool = False


class PinChange(BaseModel):
    current_pin: str = _PIN_FIELD
    new_pin: str = _PIN_FIELD
