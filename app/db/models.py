"""Modelos ORM (SQLAlchemy 2.x).

IMPORTANTE: el esquema real lo crean las migraciones SQL en `app/db/migrations/`
(no usamos autogeneración). Estos modelos son un ESPEJO MANUAL de ese SQL y deben
mantenerse sincronizados a mano. Si cambias una columna aquí, añade una migración.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Roles válidos (ver skill rgpd-dataguard, REQ-24).
WORKER_ROLES = ("empleado", "supervisor", "admin", "rlt", "inspeccion")

# Tipos de evento de jornada (ver skill fichaje-domain). En Fase 1 solo se emiten
# check_in/check_out; el resto queda definido en el esquema para no re-migrar (Fase 2).
EVENT_TYPES = (
    "check_in",
    "check_out",
    "break_start",
    "break_end",
    "travel_start",
    "travel_end",
)
MODALIDADES = ("presencial", "teletrabajo", "movil")
SOURCES = ("web", "kiosk", "mobile", "offline_sync")

# Ventanas de cómputo de la política de tiempo (REQ-12/REQ-13).
COMPUTATION_PERIODS = ("daily", "weekly", "monthly")

# Campos de time_record que se pueden corregir vía record_correction (REQ-16).
CORRECTABLE_FIELDS = ("occurred_at", "event_type", "modalidad", "travel_computes", "geo")

# Tipos y severidades de alerta de auditoría (REQ-25).
ALERT_TYPES = (
    "chain_broken",
    "login_failed",
    "account_locked",
    "mutation_attempt",
    "anomalous_access",
)
ALERT_SEVERITIES = ("info", "warning", "critical")


class Base(DeclarativeBase):
    pass


class Worker(Base):
    """Trabajador / cuenta. `code_norm` es la identificación inequívoca (REQ-05).

    No es append-only (es dato de cuenta, mutable: cambio/reset de PIN). La
    inmutabilidad aplica a `time_record` (Fase 1), no a esta tabla.
    """

    __tablename__ = "worker"
    __table_args__ = (
        CheckConstraint(
            "role IN ('empleado','supervisor','admin','rlt','inspeccion')",
            name="worker_role_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Código visible en CamelCase (legibilidad); `code_norm` en minúsculas para unicidad/login.
    code: Mapped[str] = mapped_column(String, nullable=False)
    code_norm: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)

    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)

    pin_hash: Mapped[str] = mapped_column(String, nullable=False)
    pin_temporary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    role: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'empleado'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # Lockout anti fuerza bruta (PIN corto) — REQ-21/25.
    failed_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class TimeRecord(Base):
    """Evento de jornada append-only (REQ-01). NUNCA se actualiza ni se borra (REQ-02):
    el bloqueo lo garantiza el trigger `no_mutate_time_record` en la migración 0003.

    El sellado (REQ-15) lo calcula SIEMPRE `app/audit/chain.py` (servicio único de
    escritura); ningún endpoint inserta aquí directamente.
    """

    __tablename__ = "time_record"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('check_in','check_out','break_start','break_end',"
            "'travel_start','travel_end')",
            name="time_record_event_type_check",
        ),
        CheckConstraint(
            "modalidad IN ('presencial','teletrabajo','movil')",
            name="time_record_modalidad_check",
        ),
        CheckConstraint(
            "source IN ('web','kiosk','mobile','offline_sync')",
            name="time_record_source_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    modalidad: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'presencial'")
    )
    source: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'web'"))
    geo: Mapped[str | None] = mapped_column(String, nullable=True)
    # Desplazamientos (REQ-09). Polaridad: true = ese tramo computa como tiempo efectivo
    # (no se resta); false = no computa (se resta). Solo relevante en eventos travel_*.
    travel_computes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    prev_hash: Mapped[str] = mapped_column(String, nullable=False)
    hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class TimePolicy(Base):
    """Política de cómputo de tiempo, ajustable en runtime (REQ-13, REQ-12).

    Config MUTABLE (no append-only): singleton global `id = 1`. La inmutabilidad solo
    aplica a `time_record`. Editable vía `PUT /admin/time-policy` sin tocar código.
    """

    __tablename__ = "time_policy"
    __table_args__ = (
        CheckConstraint("id = 1", name="time_policy_singleton_check"),
        CheckConstraint(
            "computation_period IN ('daily','weekly','monthly')",
            name="time_policy_period_check",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default=text("1"))
    pause_computable_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    computation_period: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'monthly'")
    )
    ordinary_hours_per_period: Mapped[float] = mapped_column(
        Numeric, nullable=False, server_default=text("160")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class RecordCorrection(Base):
    """Corrección versionada de un `time_record` (REQ-16).

    Nunca se edita el original: cada corrección es una fila nueva con motivo y autor. Es
    append-only y hash-sellada (cadena propia por trabajador) igual que `time_record`; el
    bloqueo lo garantiza el trigger `no_mutate_record_correction` (migración 0006).
    """

    __tablename__ = "record_correction"
    __table_args__ = (
        CheckConstraint(
            "field IN ('occurred_at','event_type','modalidad','travel_computes','geo')",
            name="record_correction_field_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    original_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    worker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    field: Mapped[str] = mapped_column(String, nullable=False)
    corrected_value: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prev_hash: Mapped[str] = mapped_column(String, nullable=False)
    hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class AuditAlert(Base):
    """Alerta de auditoría (REQ-25): manipulación o seguridad.

    MUTABLE (no es ledger append-only): cadena rota, fallos/bloqueos de login, intentos de
    mutación y accesos anómalos. La inmutabilidad solo aplica a `time_record`/`record_correction`.
    """

    __tablename__ = "audit_alert"
    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('chain_broken','login_failed','account_locked',"
            "'mutation_attempt','anomalous_access')",
            name="audit_alert_type_check",
        ),
        CheckConstraint(
            "severity IN ('info','warning','critical')",
            name="audit_alert_severity_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    worker_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    detail: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'warning'")
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
