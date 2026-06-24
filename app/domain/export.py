"""Construcción y serialización del informe de jornada verificable (REQ-04, REQ-19).

Lógica pura (sin BD ni HTTP): ensambla `ExportReport` desde los registros + correcciones +
totales del periodo, y lo serializa a CSV (stdlib) y a PDF (fpdf2). El informe incluye el
sellado (hash/prev_hash) de cada registro para que sea verificable y, junto a cada uno, sus
correcciones (audit-trail §3).
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import timedelta
from typing import Protocol

from fpdf import FPDF

from app.core.time import iso8601, utc_now
from app.schemas.export import ExportCorrectionRow, ExportRecordRow, ExportReport


class _Worker(Protocol):
    id: object
    code: str
    first_name: str
    last_name: str


def _minutes(td: timedelta) -> int:
    return int(td.total_seconds() // 60)


def build_report(worker: _Worker, records: list, corrections: list, summary: dict) -> ExportReport:
    """Ensambla el `ExportReport` (identificación + detalle + correcciones + totales)."""
    by_record: dict[object, list] = defaultdict(list)
    for c in corrections:
        by_record[c.original_record_id].append(c)

    rows: list[ExportRecordRow] = []
    for r in records:
        corr_rows = [
            ExportCorrectionRow(
                seq=c.seq,
                field=c.field,
                corrected_value=c.corrected_value,
                reason=c.reason,
                author_id=c.author_id,
                occurred_at=c.occurred_at,
                hash=c.hash,
            )
            for c in by_record.get(r.id, [])
        ]
        rows.append(
            ExportRecordRow(
                seq=r.seq,
                event_type=r.event_type,
                occurred_at=r.occurred_at,
                modalidad=r.modalidad,
                source=r.source,
                travel_computes=r.travel_computes,
                geo=r.geo,
                prev_hash=r.prev_hash,
                hash=r.hash,
                corrections=corr_rows,
            )
        )

    return ExportReport(
        worker_id=worker.id,
        employee_code=worker.code,
        full_name=f"{worker.first_name} {worker.last_name}",
        period=summary["period"],
        start=summary["start"],
        end=summary["end"],
        efectivo_min=_minutes(summary["efectivo"]),
        ordinarias_min=_minutes(summary["ordinarias"]),
        extra_min=_minutes(summary["extra"]),
        ordinary_min=_minutes(summary["ordinary"]),
        generated_at=utc_now(),
        records=rows,
    )


def to_csv(report: ExportReport) -> str:
    """Serializa el informe a CSV: cabecera de identificación/totales + eventos + correcciones."""
    buf = io.StringIO()
    w = csv.writer(buf)

    w.writerow(["# Informe de jornada (export verificable) - Global Meats"])
    w.writerow(["trabajador", report.full_name])
    w.writerow(["codigo_empleado", report.employee_code])
    w.writerow(["worker_id", str(report.worker_id)])
    w.writerow(["periodo", report.period])
    w.writerow(["inicio", iso8601(report.start)])
    w.writerow(["fin", iso8601(report.end)])
    w.writerow(["efectivo_min", report.efectivo_min])
    w.writerow(["ordinarias_min", report.ordinarias_min])
    w.writerow(["extra_min", report.extra_min])
    w.writerow(["ordinary_min", report.ordinary_min])
    w.writerow(["generado", iso8601(report.generated_at)])
    w.writerow([])

    w.writerow(
        ["seq", "event_type", "occurred_at", "modalidad", "source",
         "travel_computes", "geo", "prev_hash", "hash"]
    )
    for r in report.records:
        w.writerow(
            [r.seq, r.event_type, iso8601(r.occurred_at), r.modalidad, r.source,
             r.travel_computes, r.geo or "", r.prev_hash, r.hash]
        )

    w.writerow([])
    w.writerow(["# Correcciones"])
    w.writerow(
        ["record_seq", "correction_seq", "field", "corrected_value", "reason",
         "author_id", "occurred_at", "hash"]
    )
    for r in report.records:
        for c in r.corrections:
            w.writerow(
                [r.seq, c.seq, c.field, c.corrected_value, c.reason,
                 str(c.author_id), iso8601(c.occurred_at), c.hash]
            )

    return buf.getvalue()


def _ascii(text: str) -> str:
    """fpdf2 con fuente core (latin-1) no admite todo Unicode; degradamos a ASCII seguro."""
    return text.encode("latin-1", "replace").decode("latin-1")


def to_pdf(report: ExportReport) -> bytes:
    """Serializa el informe a PDF (fpdf2). Devuelve bytes (`%PDF` al inicio)."""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _ascii("Informe de jornada - Global Meats"), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    for label, value in [
        ("Trabajador", report.full_name),
        ("Codigo empleado", report.employee_code),
        ("Periodo", f"{report.period} ({iso8601(report.start)} - {iso8601(report.end)})"),
        (
            "Totales (min)",
            f"efectivo {report.efectivo_min} | ordinarias {report.ordinarias_min} | "
            f"extra {report.extra_min} | jornada {report.ordinary_min}",
        ),
        ("Generado", iso8601(report.generated_at)),
    ]:
        pdf.cell(0, 6, _ascii(f"{label}: {value}"), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, _ascii("Detalle de eventos (con sellado)"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Courier", "", 7)
    for r in report.records:
        line = (
            f"#{r.seq} {r.event_type} {iso8601(r.occurred_at)} {r.modalidad}/{r.source} "
            f"hash={r.hash[:16]}..."
        )
        pdf.cell(0, 4, _ascii(line), new_x="LMARGIN", new_y="NEXT")
        for c in r.corrections:
            corr = (
                f"    correccion #{c.seq} {c.field}={c.corrected_value} "
                f"motivo='{c.reason}' hash={c.hash[:16]}..."
            )
            pdf.cell(0, 4, _ascii(corr), new_x="LMARGIN", new_y="NEXT")

    out = pdf.output()
    return bytes(out)
