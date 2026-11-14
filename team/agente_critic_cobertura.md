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

- Transferencia confirmada; iniciando diagnóstico y reproducción antes de pruebas RED.

## Registro

- 2026-11-14: leídas reglas, plan activo, registros relevantes y skills de depuración/TDD; alcance registrado antes de editar producto.
