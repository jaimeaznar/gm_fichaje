#!/usr/bin/env python3
"""Verificación de residencia UE para deploy/CI (REQ-23).

Falla con exit code 1 si la región configurada no es de la UE. Pensado para correr
ANTES de cada despliegue: no se debe desplegar datos personales fuera de la UE.
"""

from __future__ import annotations

import sys

from app.core.config import RegionNotEUError, assert_eu_region, settings


def main() -> int:
    try:
        assert_eu_region()
    except RegionNotEUError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    print(
        "✅ Región UE verificada "
        f"(deploy={settings.deploy_region}, supabase={settings.supabase_region})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
