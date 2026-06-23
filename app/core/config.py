"""Configuración de la aplicación y verificación de residencia de datos en la UE.

REQ-23 (🟡): los datos personales deben residir en servidores de la UE. El arranque
de la app y el script de deploy FALLAN si la región configurada no es de la UE.
REQ-10 (🟢): base jurídica del tratamiento = cumplimiento de obligación legal
(art. 6.1.c RGPD); aquí solo dejamos constancia de la minimización por configuración.
"""

from __future__ import annotations

import re

from pydantic_settings import BaseSettings, SettingsConfigDict

# Allowlist de regiones consideradas dentro de la UE / EEE.
# Cubre los nombres habituales de AWS (eu-*), GCP (europe-*) y descripciones libres.
_EU_REGION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^eu[-_]", re.IGNORECASE),          # eu-west-1, eu-central-1, eu_west...
    re.compile(r"^europe[-_]", re.IGNORECASE),      # europe-west1 (GCP)
    re.compile(r"frankfurt|ireland|paris|madrid|stockholm|milan|amsterdam|zurich",
               re.IGNORECASE),
)


def is_eu_region(region: str | None) -> bool:
    """True si `region` parece pertenecer a la UE/EEE."""
    if not region:
        return False
    return any(p.search(region) for p in _EU_REGION_PATTERNS)


class RegionNotEUError(RuntimeError):
    """Se lanza cuando la región configurada no es de la UE (REQ-23)."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base de datos
    database_url: str = "postgresql+asyncpg://fichajes:localdev@localhost:5432/fichajes"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_expires_min: int = 30
    jwt_algorithm: str = "HS256"

    # Seguridad de login (PIN corto -> lockout imprescindible)
    max_failed_attempts: int = 5
    lockout_minutes: int = 15

    # Residencia de datos (REQ-23)
    deploy_region: str = "eu-west-1"
    supabase_region: str = "eu-central-1"


settings = Settings()


def assert_eu_region(s: Settings = settings) -> None:
    """Verifica que tanto el deploy como Supabase están en la UE. Lanza si no (REQ-23)."""
    offenders = []
    if not is_eu_region(s.deploy_region):
        offenders.append(f"DEPLOY_REGION={s.deploy_region!r}")
    if not is_eu_region(s.supabase_region):
        offenders.append(f"SUPABASE_REGION={s.supabase_region!r}")
    if offenders:
        raise RegionNotEUError(
            "Residencia de datos fuera de la UE (REQ-23). Regiones no válidas: "
            + ", ".join(offenders)
            + ". Los datos personales deben permanecer en servidores de la UE."
        )
