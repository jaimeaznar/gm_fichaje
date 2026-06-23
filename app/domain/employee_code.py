"""Generación del código de empleado (REQ-05).

El código de empleado es la identificación inequívoca del trabajador. Se genera a
partir del nombre con escalado determinista y desambiguación sin colisiones. La
unicidad REAL la garantiza la UNIQUE de Postgres sobre `code_norm` (ver
services/onboarding.py); aquí solo producimos candidatos en orden.

Reglas (skill onboarding-empleados, references/codigo-pin.md):
- Normalizar: quitar acentos -> ASCII, quedarse solo con letras, minúsculas.
- Primer nombre + primer apellido.
- Escalado 2+2 -> 3+3 -> ... hasta agotar letras; luego sufijo numérico.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator


def normalize(s: str) -> str:
    """Acentos fuera, solo letras a-z, en minúsculas. 'José' -> 'jose'."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z]", "", s).lower()


def first_token(s: str) -> str:
    """Primer token (para nombres compuestos: 'José Luis' -> 'José')."""
    return s.strip().split()[0] if s.strip() else ""


def candidate_codes(nombre: str, apellido: str) -> Iterator[str]:
    """Genera candidatos de código en CamelCase, de más corto a más largo.

    Nivel 2+2 ('PeGa'), 3+3 ('PepGar'), ... y al agotar letras, sufijo numérico
    sobre el nivel base ('PeGa2', 'PeGa3', ...). Nunca se queda sin salida.
    """
    n = normalize(first_token(nombre))
    a = normalize(first_token(apellido))
    if not n or not a:
        raise ValueError("Nombre y apellido deben contener al menos una letra cada uno.")

    max_level = max(len(n), len(a))
    for k in range(2, max_level + 1):
        yield n[:k].capitalize() + a[:k].capitalize()

    base = n[:2].capitalize() + a[:2].capitalize()
    i = 2
    while True:
        yield f"{base}{i}"
        i += 1
