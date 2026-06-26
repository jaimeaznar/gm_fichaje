"""Utilidades de tiempo (UTC) y semilla de sellado encadenado.

REQ-15 (🟡): los registros llevan timestamp del servidor en UTC + hash encadenado.
Aquí dejamos las primitivas (hora UTC del servidor, formato ISO-8601 y el cálculo de
hash de cadena). La cadena de hash completa sobre `time_record` vive en Fase 1
(`app/audit/chain.py`); este módulo es la base reutilizable.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

# Zona local de la empresa. Solo se usa para PRESENTACIÓN (pantallas y export):
# el almacenamiento, el sellado/hash y el cálculo de horas siguen en UTC.
MADRID = ZoneInfo("Europe/Madrid")


def utc_now() -> datetime:
    """Hora actual del servidor, timezone-aware en UTC. Nunca confiar en el cliente."""
    return datetime.now(UTC)


def iso8601(dt: datetime) -> str:
    """Formatea un datetime a ISO-8601 (el cliente formatea a su zona local)."""
    return dt.astimezone(UTC).isoformat()


def to_madrid(dt: datetime) -> datetime:
    """Convierte un datetime UTC a hora local de Madrid (DST automático).

    Solo para presentación: nunca se aplica al valor almacenado, al payload del hash
    ni al cálculo de horas (todo eso permanece en UTC).
    """
    if dt.tzinfo is None:  # defensivo: los datetimes de la BD vienen aware (timestamptz)
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(MADRID)


def chain_hash(prev_hash: str | None, payload: str) -> str:
    """Hash SHA-256 que encadena `payload` con el `prev_hash` del registro anterior.

    Semilla del sellado encadenado (REQ-15). El primer registro de una cadena usa
    prev_hash vacío. La integración con `time_record` se hace en Fase 1.
    """
    data = f"{prev_hash or ''}|{payload}".encode()
    return hashlib.sha256(data).hexdigest()
