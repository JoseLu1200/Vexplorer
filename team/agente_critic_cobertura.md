# Agente de integración del crítico de cobertura

## Identidad y autorización

- Identidad: agente IA `similarity_evaluation`; no representa a una persona.
- Autorización: delegación explícita de `/root` y transferencia confirmada por `similarity_backend` el 2026-11-14.

## Alcance y reservas

- Propiedad exclusiva: `backend/app/general_furniture/autonomous.py`, `backend/tests/test_general_furniture_autonomous.py`, un test nuevo propio si resulta necesario y este registro.
- Solo lectura: contratos, `evidence_accounting.py`, `context_payload.py`, propuesta/live/API, referencias privadas y artefactos de evaluación.
- No se usarán ground truth, sidecars, respuestas privadas ni valores específicos de casos; el runtime recibe únicamente DXF y evidencia derivada permitida.
- Sin commits, despliegue ni suite global; coordinación ejecuta la verificación integral.

## Tarea

Integrar el informe contable y el contexto crítico compacto en la generación/revisión autónoma. Exigir revisión dirigida de existencia y disposición de evidencia sin autoconfirmar componentes, identidad física, cantidades ni fabricabilidad. Preservar checkpoints parciales y la última propuesta/draft incompleta al agotar presupuesto.

## Dependencias y avisos

- `similarity_backend` congeló los archivos transferidos y publicó `build_evidence_accounting_report`.
- `public_integration` publicó `build_compact_review_context` y `build_region_visual_links`.
- Cualquier discrepancia contractual se coordinará antes de editar otros archivos.

## Estado

- Integración y pruebas focales completadas; pendiente revisión final Astra y verificación coordinada de raíz.

## Registro

- 2026-11-14: leídas reglas, plan activo, registros relevantes y skills de depuración/TDD; alcance registrado antes de editar producto.
- 2026-11-14: causa raíz confirmada: el crítico serializaba proposal/draft completos, no recibía accounting ni targets de existencia/disposición y el gate solo exigía cotas/hardware.
- 2026-11-14: RED observado en 4 pruebas nuevas: snapshot completo duplicado, ausencia de gate requerido, duplicate_projection aceptable con check genérico y accounting no bloqueante.
- 2026-11-14: integrado contexto compacto, enlaces visuales por región, accounting y targets exactos. Full proposal/draft queda únicamente en `repair_requested`; tras reparar se vuelve al contexto compacto.
- 2026-11-14: acceptance alineado con evaluación: piezas de corte requieren kind/existence/geometry/L/W/T/quantity; hardware kind/existence/quantity sin inventar cotas; material/finish no bloquean coherencia geométrica. Abstenciones permanecen incomplete.
- 2026-11-14: asignaciones multi-región y duplicados requieren duplicate_scan/cross_view dirigido; checks multitarjeta se permiten solo si incluyen cada target exacto y cada target conserva field_review individual.
- 2026-11-14: `python -m pytest` focal sobre critic/autonomous/accounting/context/live/proposal → 66 passed; Ruff limpio. Sin suite global, llamadas live, GT, sidecars, commits ni despliegue.
- 2026-11-14: revisión independiente Astra acotada al diff autonomous/critic → `SHIP`; confirmó invariantes de cut pieces, hardware, abstención y multi-región/duplicados. La redundancia menor de targets hardware señalada quedó eliminada antes del handoff.
