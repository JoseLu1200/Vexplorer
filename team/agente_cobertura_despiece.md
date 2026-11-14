# Agente cobertura de despiece — propuesta live

## Identidad y autorización

- Identidad: agente IA `similarity_backend`, delegado por `/root` para esta corrección.
- Rol: backend del proponente live y accounting de evidencia.
- Fecha: 2026-11-14.

## Tarea y alcance

- Objetivo: evitar que el proponente omita evidencia candidata sin explicación y exponer fallos de cotas trazables, sin confundir contornos con piezas físicas.
- Estado: implementación live y helper puro completados y verificados.
- Propiedad final: `evidence_accounting.py`, `live.py`, propagación en `proposal.py`, prueba focal `test_general_furniture_evidence_accounting.py` y este registro, únicamente dentro de `.worktrees/similarity-public`.
- Dependencias solo lectura: contratos, geometría, artefactos permitidos `.runtime/complex-visual-audit` del checkout raíz.
- Fuera de alcance: contratos Pydantic, `main.py`, storage/API, frontend, referencias privadas/ground truth, commits y despliegue.
- Transferencias explícitas: `context_payload.py` pertenece a `/root/public_integration`; `autonomous.py` y sus pruebas pertenecen a `/root/similarity_evaluation`; `storage.py` permanece en `/root/library_api`.

## Diagnóstico

- Los resultados parciales permitidos citan 36/40 y 21/31 contornos cerrados. Esos cocientes son solo diagnóstico de evidencia citada: no miden recall de piezas.
- El contexto no publica cierre `eligible/assigned/unexplained`; el materializador valida referencias pero no cobertura.
- El crítico solo revisa componentes ya propuestos y no exige existencia de paneles; ambos runs agotaron tiempo antes de producir snapshot crítico.
- No se consultaron referencias reservadas ni se introducirán respuestas de casos concretos en runtime/prompts.

## Diseño implementado

- Deriva regiones candidatas deterministas de contornos cerrados no degenerados, con autoridad explícita `candidate_evidence_not_physical_piece`.
- Exige una disposición tipada por región: `assigned`, `duplicate_projection`, `nonmaterial` o `unresolved`; valida cardinalidad, fuentes exactas y referencias de ledger.
- Reporta dimensiones ausentes o sin trazabilidad y componentes que reclaman múltiples regiones; estos últimos requieren revisión dirigida de cada región para impedir que un único panel salde evidencia disjunta sin crítica.
- `evidence_coverage` es accounting, nunca precisión/recall físico ni criterio de autoaceptación.
- El proponente recibe reparación acotada. Si agota presupuesto, conserva la última propuesta/draft válida como incompleta junto al informe; no inventa cotas ni descarta todo el resultado.
- La crítica autónoma y el contexto compacto se integran por sus propietarios transferidos; no se editaron aquí.
- El snapshot de revisión propaga las `evidence_dispositions` exactas de su fuente constructiva, de modo que el contrato puede aceptar solo `evidence_region:<id>` pertenecientes a esa propuesta.
- El proveedor fake integral se actualizó al contrato actual con parámetros estimated acotados, disposiciones exactas y reviews requeridas; no se mockeó ni debilitó el motor.

## Pruebas y cierre

| Caso | Comando | Resultado | Límite |
|---|---|---|---|
| Diagnóstico de artefactos | extracción local de conteos desde propuestas y DXF permitidos | 36/40 y 21/31 contornos citados | no es evaluación contra GT ni recall físico |
| Accounting + live + materialización + contexto | `python -m pytest backend/tests/test_general_furniture_evidence_accounting.py backend/tests/test_general_furniture_live.py backend/tests/test_general_furniture_proposal.py backend/tests/test_general_furniture_context_payload.py -q` | 31 passed | suite focal; integración global corresponde a `/root` |
| Recovery + live + accounting | `python -m pytest backend/tests/test_job_recovery.py backend/tests/test_general_furniture_live.py backend/tests/test_general_furniture_evidence_accounting.py -q` | 24 passed | recuperación reanuda crítico sin repetir proponente |
| Integración producción general | `python -m pytest backend/tests/test_integral_api_integration.py::test_production_job_integrates_general_review_derived_and_history_persistently -q` | 1 passed | cubre persistencia y flujo integral |

- Sin commits ni despliegue. No se usaron respuestas privadas/GT ni reglas específicas para 030/016.

## Corrección de recuperación R1

- El trace público de `plank-016` mostró una propuesta tipada y materializable que se descartó por accounting incompleto; después hubo ocho inspecciones y el proveedor terminó `provider_response_incomplete`. La recuperación anterior solo conservaba el borrador si llegaba otra propuesta una vez agotadas las reparaciones.
- `live.py` retiene ahora el último par propuesta/borrador materializable antes de solicitar reparación. Si después termina el proveedor, vence un presupuesto o se agotan las reparaciones, devuelve ese par marcado en traza como incompleto junto con el informe de accounting; no lo acepta ni rellena piezas o cotas.
- Las respuestas posteriores de inspección quedan acotadas por el presupuesto de reparación. Con el límite de producción observado se permiten dos respuestas tras el borrador y luego se conserva, evitando el bucle de ocho inspecciones de R1.
- `evidence_accounting.py` asocia cada región inválida con un motivo estable (`missing_source`, conflicto de componente, proyección no respaldada, etc.) para reparación dirigida. Las regiones siguen siendo evidencia candidata, nunca ocurrencias ni recall físico.
- TDD observado: tres pruebas nuevas fallaron antes de implementar (motivo regional ausente, pérdida ante proveedor incompleto y bucle de inspecciones) y pasaron tras el cambio.
- Verificación focal: `python -m pytest backend/tests/test_job_recovery.py backend/tests/test_general_furniture_evidence_accounting.py backend/tests/test_general_furniture_live.py backend/tests/test_general_furniture_proposal.py -q` → 34 passed. `ruff check` de archivos propios y `git diff --check` sin errores.
