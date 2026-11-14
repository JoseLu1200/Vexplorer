# Agente semántica v2 montaje — grafo estructural

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA `semantica_v2_montaje`; no representa a una persona.
- Rol: auditar y corregir la semántica de relaciones de montaje.
- Archivo creado por delegación explícita de `/root` el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto: explicar el grafo vacío/desconocido, separar soporte funcional de unión oculta y cerrar validaciones comprobables sin leer referencias privadas.
- Referencia del plan: reparación semántica v2 solicitada por el usuario.
- Estado: implementación propia terminada; pendiente integración conjunta y auditoría.

## Alcance y reservas

- Archivos que puedo editar: `backend/app/general_furniture/assembly_semantics.py`, `backend/tests/test_general_furniture_assembly_semantics.py` y este registro.
- Dependencias que solo leeré: `backend/app/contratos/modelos.py`, `backend/app/general_furniture/live.py`, `proposal.py`, `autonomous.py`, `review.py` y pruebas públicas relacionadas.
- Archivos compartidos que requieren coordinación: `live.py`, `proposal.py` y `autonomous.py` pertenecen al agente de inferencia; `review.py` al coordinador; `contratos/` no se modifica.
- Solapes detectados y acuerdo: reservas anteriores de cierre constan liberadas; el nuevo alcance fue asignado explícitamente por `/root`.

## Hecho en el último bloque

- Trazado el flujo proposal → validación → draft → review y revisada evidencia pública, sin abrir holdout ni referencias privadas.
- Identificado que el validador actual solo cierra referencias y que el prompt confunde `supported_by` con `fixed_to` como alternativas incompatibles.
- Se probó y retiró una restricción de duplicación de fuentes por extremo: el contrato permite evidencia relacional propia, y una vista puede contener los contornos de ambos componentes sin copiarse literalmente en ellos.
- Se conserva la abstención `unknown/conflict` sin fuente obligatoria; exigirla incentivaría referencias inventadas. `assembly_semantics.py` no se atribuye la corrección del grafo.
- Auditado el cambio real en inferencia: inventario/roles canónicos, soporte funcional separado de joinery y directivas cerradas de reparación para pares existentes.

## Siguiente bloque

- Recibir auditoría independiente e integrar la corrección de prompt realizada por el propietario de inferencia.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo |
|---|---|---|---|
| 2026-11-14 | No inferir aristas desde roles ni texto libre | Un rol o una coincidencia visual no demuestra contacto ni unión | Arquitectura y delegación de `/root` |
| 2026-11-14 | Tratar soporte funcional y fijación como ejes compatibles, no alternativas excluyentes | Un tablero puede estar soportado y fijado simultáneamente | Semántica de las relaciones actuales |
| 2026-11-14 | Permitir `unknown/conflict` sin `source_refs` | La abstención no debe forzar evidencia inexistente | Revisión de `/root` |
| 2026-11-14 | No exigir que `source_refs` de relación se dupliquen en ambos componentes | Los espacios de evidencia son independientes y existen referencias equivalentes por jerarquía vista→contorno | Auditoría independiente y reproducción RED |

## Dependencias / avisos

- Necesito de: agente propietario de inferencia para integrar cualquier regla de cobertura en `live.py`/`proposal.py`/`autonomous.py`.
- Afecta a: generación live y evaluación semántica del grafo.
- Aviso realizado: diagnóstico y diseño enviados a `/root` el 2026-11-14.
- Cambio de `contratos/`: no aplica; prohibido por el alcance.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| RED focal inicial | `.venv\Scripts\python.exe -m pytest -q backend/tests/test_general_furniture_assembly_semantics.py` | 2 failed, 7 passed | Las dos restricciones candidatas resultaron demasiado fuertes tras revisión |
| RED de evidencia equivalente | mismo comando | 1 failed, 7 passed | Una vista relacional válida contenía contornos distintos de ambos componentes |
| GREEN focal final | mismo comando | 8 passed | Restricciones artificiales retiradas; 1 warning ajeno de deprecación Starlette/httpx |
| Regresión montaje/propuesta/revisión | `python -m pytest -q backend/tests/test_general_furniture_assembly_semantics.py backend/tests/test_general_furniture_proposal.py backend/tests/test_general_furniture_review.py` | 19 passed | Python de sistema, sin red |
| Integración previa | `.venv\Scripts\python.exe -m pytest -q backend/tests/test_general_furniture_proposal.py backend/tests/test_general_furniture_live.py backend/tests/test_general_furniture_autonomous.py backend/tests/test_general_furniture_review.py` | 42 passed | Antes de cambios concurrentes de inferencia |
| Integración concurrente | focales assembly/proposal/live/review | 29 passed, 2 failed | RED ajeno esperado: dos pruebas nuevas de prompt live aún sin implementación |
| Suite completa | `.venv\Scripts\python.exe -m pytest -q` | error de colección | Cambio concurrente: test importa `_semantic_repair_directives` todavía ausente en `autonomous.py` |
| Integración freeze inferencia | `python -m pytest -q backend/tests/test_general_furniture_live.py backend/tests/test_general_furniture_autonomous.py backend/tests/test_general_furniture_assembly_semantics.py` | 48 passed | Sin proveedor real ni holdout |
| Lint focal propio | `python -m ruff check backend/app/general_furniture/assembly_semantics.py backend/tests/test_general_furniture_assembly_semantics.py` | All checks passed | Ruff 0.15.20 del Python de sistema |
| Lint freeze amplio | `python -m ruff check` sobre live/autonomous y pruebas focales | 4 F841 | Variables no usadas en prueba autónoma líneas 384, 526, 611 y 694; fuera de alcance propio |

## Bloqueos y cierre

- Bloqueos: ninguno propio. La efectividad sobre proveedor real sigue sin medirse en esta sesión.
- Pendientes: suite global conjunta y medir el proveedor real sin referencias privadas.
- Reservas liberadas: `assembly_semantics.py` y su prueba focal, 2026-11-14.
- Entrega a otra persona: causas, límites y verificación comunicados a `/root`, `diagnostico_inferencia` y `auditoria_independiente`.
