"""Verificador periódico de la cadena de hash (REQ-25).

Recorre todos los trabajadores y recomputa sus cadenas (`time_record` y `record_correction`).
Por cada rotura emite una `audit_alert(chain_broken, critical)`. Se expone como endpoint admin
(`POST /admin/audit/verify`) y como job de cron:

    python -m app.audit.verify
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.alerts import record_alert
from app.audit.chain import verify_chain, verify_correction_chain
from app.db.models import TimeRecord
from app.db.session import SessionLocal, engine


async def verify_all(db: AsyncSession) -> dict:
    """Verifica las cadenas de todos los trabajadores; alerta ante cada rotura."""
    worker_ids = (
        await db.execute(select(TimeRecord.worker_id).distinct())
    ).scalars().all()

    broken: list[dict] = []
    for worker_id in worker_ids:
        ok, seq = await verify_chain(db, worker_id)
        if not ok:
            broken.append({"worker_id": str(worker_id), "kind": "time_record", "seq": seq})
            await record_alert(
                db,
                "chain_broken",
                f"Cadena de time_record rota en seq={seq}",
                worker_id=worker_id,
                severity="critical",
            )
        ok_c, seq_c = await verify_correction_chain(db, worker_id)
        if not ok_c:
            broken.append(
                {"worker_id": str(worker_id), "kind": "record_correction", "seq": seq_c}
            )
            await record_alert(
                db,
                "chain_broken",
                f"Cadena de record_correction rota en seq={seq_c}",
                worker_id=worker_id,
                severity="critical",
            )

    return {"checked": len(worker_ids), "broken": broken}


async def _main() -> None:
    async with SessionLocal() as db:
        result = await verify_all(db)
    if result["broken"]:
        print(f"⚠️  {len(result['broken'])} cadena(s) rota(s): {result['broken']}")
    else:
        print(f"✅ {result['checked']} trabajador(es) verificados, sin roturas.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
