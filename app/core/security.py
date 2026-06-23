"""Seguridad: PIN (bcrypt), JWT y utilidades anti fuerza bruta.

REQ-05 (🟢): identificación inequívoca (código de empleado) + autenticación por PIN
  con hash bcrypt. El PIN nunca se guarda ni se loguea en claro.
REQ-21 (🟡): sin biometría; bcrypt como mecanismo de autenticación.
El lockout por intentos fallidos (PIN de 6 dígitos -> espacio pequeño) es
imprescindible; la emisión de `audit_alert` se cablea en Fase 4.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.core.time import utc_now

# PINs triviales prohibidos (ver onboarding-empleados/references/codigo-pin.md).
TRIVIAL_PINS = {"000000", "111111", "123456", "654321", "112233", "121212", "098765"}

PIN_LENGTH = 6


# ---- PIN: hash y verificación (bcrypt) ----

def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin: str, pin_hash: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode(), pin_hash.encode())
    except (ValueError, TypeError):
        return False


# ---- Generación y validación de PIN ----

def is_trivial_pin(pin: str, code_norm: str = "") -> bool:
    """True si el PIN es demasiado adivinable y debe rechazarse."""
    if len(pin) != PIN_LENGTH or not pin.isdigit():
        return True
    if pin in TRIVIAL_PINS:
        return True
    if len(set(pin)) == 1:  # 000000, 111111...
        return True
    if code_norm and pin == code_norm[:PIN_LENGTH]:  # no derivable del código
        return True
    return False


def generate_pin(code_norm: str = "") -> str:
    """PIN inicial de 6 dígitos, criptográficamente seguro y no trivial (`secrets`)."""
    while True:
        pin = f"{secrets.randbelow(1_000_000):06d}"
        if not is_trivial_pin(pin, code_norm):
            return pin


# ---- JWT ----

def create_access_token(worker_id: str, role: str, pin_temporary: bool) -> str:
    """Emite un JWT con claims `worker_id`, `role` y `pin_temporary` (REQ-05)."""
    now = utc_now()
    payload = {
        "worker_id": worker_id,
        "role": role,
        "pin_temporary": pin_temporary,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_min),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decodifica y valida un JWT. Lanza `jwt.PyJWTError` si es inválido/expirado."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
