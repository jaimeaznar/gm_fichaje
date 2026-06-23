#!/usr/bin/env python3
"""Crea el primer administrador (bootstrap).

`POST /admin/workers` exige rol admin, así que el primer admin se crea por aquí.
Imprime el código de empleado y el PIN inicial UNA sola vez.

Uso:
    python -m scripts.seed_admin "Nombre" "Apellido"
"""

from __future__ import annotations

import asyncio
import sys

from app.db.session import SessionLocal, engine
from app.services.onboarding import create_employee


async def _main(first_name: str, last_name: str) -> None:
    async with SessionLocal() as db:
        created = await create_employee(db, first_name, last_name, role="admin")
    await engine.dispose()
    print("Administrador creado:")
    print(f"  employee_code: {created.employee_code}")
    print(f"  PIN inicial  : {created.pin}  (se muestra UNA sola vez)")
    print("  Cambia el PIN en el primer login (pin_temporary=True).")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python -m scripts.seed_admin \"Nombre\" \"Apellido\"", file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(_main(sys.argv[1], sys.argv[2]))
