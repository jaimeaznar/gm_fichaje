"""Modelos ORM (SQLAlchemy 2.x).

IMPORTANTE: el esquema real lo crean las migraciones SQL en `app/db/migrations/`
(no usamos autogeneración). Estos modelos son un ESPEJO MANUAL de ese SQL y deben
mantenerse sincronizados a mano. Si cambias una columna aquí, añade una migración.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Roles válidos (ver skill rgpd-dataguard, REQ-24).
WORKER_ROLES = ("empleado", "supervisor", "admin", "rlt", "inspeccion")


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
