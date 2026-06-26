# Mejora — Input adaptativo en la pantalla de corrección (panel admin)

> Refinamiento de la pantalla de corrección de la Fase 7. No cambia lógica de negocio ni
> backend: es UX + robustez del frontend. El backend ya valida `corrected_value` según
> `field` (Fase 4) y queda como segunda red.

## Problema

En la pantalla de corrección, `corrected_value` es un único input de texto libre. El admin
tiene que conocer de memoria el formato según el campo que corrige (timestamp ISO para
`occurred_at`, valores exactos de enum para `event_type`/`modalidad`, `true/false` para
`travel_computes`). El formato no se indica en la interfaz y un error solo se detecta al
enviar (422). Es propenso a fallos y poco amigable.

## Objetivo

Que el input de `corrected_value` **se adapte al campo seleccionado**, imponiendo el
formato correcto desde la interfaz en lugar de depender de que el admin lo recuerde.

## Comportamiento por campo

Al elegir `field` en el formulario de corrección, el control de `corrected_value` cambia:

| field | Control | Detalle |
|-------|---------|---------|
| `occurred_at` | **Date-time picker**: calendario para el día + selector de hora y minutos | Se serializa a ISO-8601 con zona (UTC) antes de enviar |
| `event_type` | **Desplegable** | 6 opciones: check_in, check_out, break_start, break_end, travel_start, travel_end |
| `modalidad` | **Desplegable** | 3 opciones: presencial, teletrabajo, movil |
| `travel_computes` | **Toggle / checkbox** | Sí/No → envía `"true"` / `"false"` |
| `geo` | **Texto libre** | Único caso que sigue siendo input de texto |

Mientras no se elija `field`, el control de valor puede quedar deshabilitado o neutro.

## Detalles de implementación (Jinja2 + Alpine.js, stack `frontend-fichaje`)

- El cambio de control se gobierna con **Alpine.js** en el cliente: un `x-data` con el
  `field` seleccionado y un `x-if`/`x-show` que muestra el control adecuado. Sin build de
  JS (coherente con la skill).
- **Serialización antes de enviar** (clave): el valor que viaja al backend en
  `corrected_value` debe seguir siendo el **string** que el backend ya espera:
  - `occurred_at`: el picker compone el string ISO-8601 en UTC (p. ej.
    `2026-06-24T08:05:00Z`). Si el picker trabaja en hora local, convertir a UTC antes de
    serializar (el backend sella en UTC; ojo a la zona de Madrid).
  - `event_type` / `modalidad`: el value del desplegable es exactamente el valor del enum.
  - `travel_computes`: el toggle se serializa a `"true"` / `"false"` en minúscula.
  - `geo`: texto tal cual.
- El envío sigue siendo vía htmx al endpoint existente
  `POST /records/{record_id}/corrections` (sin cambios de API).
- Los valores de los desplegables **no se hardcodean a mano** si es posible: tomarlos de
  las constantes que ya existen en el backend (`EVENT_TYPES`, `MODALIDADES`) — exponerlas a
  la plantilla o renderizarlas server-side, para que si el dominio cambia, el desplegable no
  quede desincronizado.
- `reason` (obligatorio) y el resto del formulario de corrección no cambian.

## Criterios de aceptación

- Seleccionar `occurred_at` muestra calendario + hora/minutos; el valor enviado es ISO-8601
  UTC válido y el backend lo acepta (no 422 por formato).
- Seleccionar `event_type` o `modalidad` muestra un desplegable con exactamente las opciones
  válidas; no es posible enviar un valor fuera del enum desde la interfaz.
- Seleccionar `travel_computes` muestra un toggle; envía `"true"`/`"false"`.
- Seleccionar `geo` muestra texto libre.
- La validación del backend sigue intacta como segunda red (un envío manipulado con formato
  inválido sigue devolviendo 422).
- La conversión de zona horaria es correcta: una hora elegida en horario de Madrid se guarda
  como el instante UTC equivalente.

## Fuera de alcance

- No se toca el backend ni la API de correcciones (Fase 4) — solo la plantilla y el JS de
  cliente de la pantalla de corrección.
- No se cambia el modelo de datos ni la validación de `corrected_value`.

## Prompt sugerido para Claude Code

> Read the `frontend-fichaje` skill and the existing correction screen from Fase 7. Improve
> the `corrected_value` input so it adapts to the selected `field`: a date-time picker
> (calendar for the day + hour/minute selector) for `occurred_at`, a dropdown for
> `event_type` (6 values) and `modalidad` (3 values), a toggle for `travel_computes`, and
> free text only for `geo`. Use Alpine.js, no JS build. Serialize each control back to the
> string format the backend already expects (ISO-8601 UTC for occurred_at — convert from
> Madrid local time to UTC; exact enum value for the dropdowns; "true"/"false" for the
> toggle). Pull the dropdown options from the existing backend constants (EVENT_TYPES,
> MODALIDADES) rather than hardcoding them. Don't touch the corrections API or backend
> validation — that stays as the second safety net. Plan it first, don't implement yet.