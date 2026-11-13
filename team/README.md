# Equipo

Un archivo `team/<nombre>.md` por integrante, creado desde [`_TEMPLATE.md`](_TEMPLATE.md). Reglas completas en [`../CLAUDE.md`](../CLAUDE.md).

**Para editar código hay que haber creado tu archivo o designado uno existente de forma explícita.** Sin él, Claude solo lee y explica.

## Roles (de `initial-plan.md`)

| Rol | Responsabilidad | Zona principal |
|-----|-----------------|----------------|
| A | Ingesta y motor geométrico (la parte más crítica) | `backend/app/ingesta/`, `backend/app/geometria/` |
| B | Herramientas, agente y validador | `backend/app/herramientas/`, `agente/`, `validador/` |
| C | Frontend: tabla, traza en vivo, visor three.js | `frontend/` |
| D | Planos de prueba, pitch y plan B de la demo (si hay 4º) | `data/planos_demo/`, documentación |

**Zona compartida:** `backend/app/contratos/` (modelos Pydantic de piezas y contornos). Solo se cambia con acuerdo entre A y B, avisando a C.

## Integrantes

<!-- Añade una fila al crear tu archivo. -->

| Persona | Rol | Archivo | Tarea actual |
|---------|-----|---------|--------------|
| _(nadie registrado aún)_ | | | |
