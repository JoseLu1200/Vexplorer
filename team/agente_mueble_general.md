# Agente mueble general — interpretación revisable

## Identidad y autorización

- Nombre declarado por el usuario: agente mueble general de IA; no representa a una persona.
- Rol: backend de interpretación genérica, delegado por el coordinador del swarm GPT-6.1 Sol.
- Archivo creado o designado explícitamente: `team/agente_mueble_general.md`, solicitud del usuario del 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto vigente: completar muebles desde vistas CAD 2D con cotas escasas mediante parámetros observados, deducidos y estimados, piezas necesarias, restricciones y planos 2D acotados.
- Referencia del plan: brechas de T11–T13 y flujo operacional propuesta → revisión → BOM/planos/3D/base de coste.
- Estado: contrato CAD-completion congelado y aprobado; implementación TDD en `.worktrees/cad-completion` iniciada desde `0e65713`.

## Alcance y reservas

- Archivos o carpetas que puedo editar: nuevos módulos bajo `backend/app/general_furniture/`, nuevas pruebas `backend/tests/test_general_furniture_*.py`, este registro y, solo tras acuerdo A/B, `backend/app/contratos/modelos.py`.
- Dependencias que solo leeré: ingesta, geometría, servicios, salidas, agente y economía existentes.
- Archivos compartidos que requieren coordinación: `backend/app/contratos/modelos.py` con A/B y aviso a frontend/coordinador.
- Solapes detectados y acuerdo para resolverlos: no se editó `main.py` ni economía; `provider.py` se amplió de forma retrocompatible tras coordinación con integración/root.

## Hecho en el último bloque

- Pipeline genérico implementado: medidas deterministas de contornos, propuesta native-tool, materialización hipotética, revisión replace/split/merge/drop, snapshots SQLite inmutables y derivados BOM/CSV/JSON/SVG/DXF/escena/base de coste.
- Router aislado con CAS de propuestas, revisiones exactas, actor autenticado prevalente, envelopes y artefactos descargables; `main.py` queda en integración.
- Smoke real inicial detectó propuestas sin dimensiones; se corrigió el prompt/esquema para autorizar `measurement:<id>` sin convertir la asignación semántica en observación.
- El target histórico conserva `required_cost_scope` y `required_hours_scope` elegidos por la persona; no mezcla alcances ni los infiere de comparables.
- Flujo proponente-critico con imagenes reales, marcas vinculadas al ledger, regiones/correspondencias ambiguas y una reparacion P2 materializada contra el mismo ledger.
- Revision de maquina y estado epistemico permanecen ortogonales; cantidades hypothesis solo generan `scenario_occurrences`, nunca ocurrencias fisicas o coste fiable.
- Ruta `/auto-review` con CAS y ejecucion directa deshabilitada por defecto; la integracion durable conserva P1, P2 y review.

## Siguiente bloque

- Materializar modelos compactos (32 parámetros, 64 componentes, 128 restricciones/detalles, DAG profundidad 8), resolver bindings `parameter:`, integrar propuesta/crítica/derivados y entregar F01 ejecutable.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Pipeline genérico aditivo, separado del de mesa | Evita romper flujos existentes y conserva semántica honesta por evidencia | Delegación del coordinador |
| 2026-11-14 | Ocurrencias solo desde cantidad revisada; vistas nunca cuentan piezas | Separa representación de objetos físicos | Acuerdo A/B explícito |
| 2026-11-14 | Asignar una medida observada a un campo de componente conserva estado hypothesis | La geometría no prueba semántica ni montaje | Hallazgo de smoke/revisión root |
| 2026-11-14 | `auto_review_status` es metadato ortogonal, no un estado factual auto-confirmado | Evita que consumidores confundan proceso con verdad | Acuerdo root/Astra/A-B |
| 2026-11-14 | Una reparacion semantica crea P2 inmutable y vuelve a criticarse | Reintentar JSON no corrige bindings, agrupacion o cantidad | Gate root/Astra |
| 2026-11-14 | Un único escenario constructivo provisional alimenta BOM y planos; `estimated` aceptado conserva su número/rango | El usuario exige una propuesta útil, no una lista vacía de unknowns | Especificación CAD-completion y freeze root/A-B |
| 2026-11-14 | Una deducción transitivamente dependiente de estimación sigue `estimated` | Cerrar una ecuación no eleva la autoridad de sus entradas | Freeze root/Astra |
| 2026-11-14 | Toda cota numérica de componente requiere decisión explícita del crítico; aceptar un parámetro no acepta su asignación al campo | Evita que una omisión editorial vacíe BOM y planos, sin promover parámetros automáticamente | Reproducción pública F02 + acuerdo root/Astra/evaluación |
| 2026-11-14 | Un herraje tipado requiere decisión visual explícita sobre `kind` o `geometry` | Permite separar piezas comerciales de piezas fabricadas sin heurísticas por nombre ni cotas inventadas | Acuerdo root/Astra/evaluación |

## Dependencias / avisos

- Necesito de: agente de geometría/ingesta para acuerdo A/B sobre campos nuevos; frontend para shape consumible.
- Afecta a: contratos Pydantic, futura API y UI de revisión.
- Aviso realizado: arquitectura/API comunicada a root, integración, frontend, economía, evaluación y operación; shapes finales comunicados de nuevo tras CAS/envelopes.
- Cambio de `contratos/`: acuerdo explícito A/B recibido de ingesta antes de escribir; frontend avisado antes del delta.
- CAD-completion: root aprobó freeze; economy/ingestion aceptaron consumir contratos sin escribirlos; frontend, integration y evaluación recibieron shapes exactos. Propiedad propia: `modelos.py`, inferencia/materialización, live/autonomous, derivations y tests; no editar validation/planner/renderer/main/router/frontend/evaluation.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Pipeline general focal | `python -m pytest backend/tests/test_general_furniture_*.py -q` (rutas explícitas en ejecución) | 27 passed; después se añadieron casos de segunda revisión, quantity hypothesis y cuotas | Smoke real final corregido pendiente de root |
| Suite Python compartida | `python -m pytest -q` | 524 passed in 66.12s | Posterior repairability focal: live+contract 10 passed |
| Sintaxis/compilación | `git diff --check`; `python -m compileall -q ...` | exit 0 | Worktree compartido contiene cambios de otros agentes |
| Autonomo, visual y derivados | `python -m pytest backend/tests/test_general_furniture_live.py backend/tests/test_general_furniture_autonomous.py backend/tests/test_general_furniture_derivations.py backend/tests/test_general_furniture_visual_evidence.py backend/tests/test_general_furniture_drawing_renderer.py -q` | 22 passed | Smoke real publico delegado a root |
| Cobertura crítica F02 y clasificación hardware | `python -m pytest -q backend/tests/test_general_furniture_autonomous.py backend/tests/test_general_furniture_derivations.py backend/tests/test_general_furniture_construction_planner.py backend/tests/test_integral_api_integration.py`; `ruff check backend/app/general_furniture/autonomous.py backend/tests/test_general_furniture_autonomous.py backend/tests/test_integral_api_integration.py` | 59 passed; Ruff limpio. Astra revalidó 31/31 focales | Inferencia real final delegada a root sobre candidato empaquetado |

## Bloqueos y cierre

- Bloqueos: ninguno propio; Astra confirmó sin blocker residual cantidad nativa, feedback reparable y scope económico genérico. La migración de fixtures históricos pertenece a economía.
- Pendientes: reinicio del servidor y resultados del smoke `measurement:` por coordinación.
- Reservas liberadas: ninguna.
- Entrega a otra persona: `create_general_furniture_router`, `GeneralFurnitureRepository`, `GeneralFurnitureContext` y rutas/revisions entregadas a integración; HTTP/envelopes entregados a frontend; DB entregada a operación.
