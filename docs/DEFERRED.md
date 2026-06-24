# Decisiones diferidas y deuda técnica conocida

Registro vivo de decisiones aplazadas. **Consultar al planificar cada nueva fase** para
reconsiderar los pendientes en el momento oportuno (ver `CLAUDE.md`). Una entrada por ítem.

- **Validación legal de "puesta a disposición" / `travel_computes` (Fase 2)** — la spec resta el
  tiempo de desplazamiento que no computa; confirmar con abogado laboralista contra el ET.
- **Compensación de horas extra, abono vs descanso (Fase 3)** — hoy marcado "pending"; el registro
  inmutable/sellado de esa decisión queda diferido a una fase posterior.
- **REQ-26 horas complementarias (Fase 3)** — diferido hasta modelar `relation_type` (contratos a
  tiempo parcial) en el trabajador.
- **Cifrado del campo `geo` al corregirlo (Fase 4)** — confirmar que corregir `geo` no salta el
  cifrado; revisar en Fase 6 cuando entre la geolocalización real.
- **FK `retention_log.worker_id` (Fase 5)** — al implementar el borrado físico de `time_record`,
  asegurar que el FK no bloquea el borrado ni deja el log huérfano (probablemente
  `ON DELETE SET NULL`); además es un punto RGPD (derecho de supresión vs deber de conservación
  4 años).
