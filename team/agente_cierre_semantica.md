# Agente cierre semántica — evaluación offline

## Identidad y autorización

- Identidad: agente de IA delegado; no representa a una persona.
- Rol: implementar evaluación semántica offline independiente.
- Archivo creado por delegación explícita de `/root` el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: medir función, ocurrencias físicas, relaciones de montaje, piezas omitidas, alternativas válidas y ambigüedad sin convertir alineación geométrica en verdad semántica.
- Referencia: `docs/superpowers/plans/2026-11-14-poc-closure.md`, bloque Semántica.
- Estado: terminado; listo para integración.

## Alcance y reservas

- Propiedad exclusiva: nuevos `evaluation/semantic*.py`, `tools/evaluate_semantic*.py`, `tests/test_semantic_evaluation*.py`, `docs/EVALUACION_SEMANTICA.md` y este registro.
- Solo lectura: runtime, contratos, corpus y referencias ajenas.
- `evaluation/metrics.py` solo se tocará si resulta imprescindible y se avisará antes a `/root`.
- Solapes: ninguno en las rutas nuevas; contrato offline coordinado con `/root/cierre_corpus`.

## Hecho en el último bloque

- Implementado contrato y scoring offline para roles, ocurrencias, montaje, alternativas, ambigüedad y cobertura de desconocidos.
- Añadido adaptador nativo individual y por benchmark pareado. La fase final usa `effective_proposal_outcome` y solo publica cantidades aceptadas por el crítico.
- Los casos fallidos permanecen en el manifiesto. Los freezes usan creación exclusiva y SHA exacto antes de abrir referencias privadas.

## Siguiente bloque

- Entregar interfaz y evidencia a `/root`; atender regresiones de la suite conjunta.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-14 | `schema_version`, `scenario_id`, referencia privada, predicción y desconocidos explícitos | Evaluar sin fuga ni IDs ocultos | Acuerdo con `/root/cierre_corpus` |
| 2026-11-14 | `certification: design_known_synthetic` para fixtures sintéticos | No atribuir certificación técnica humana inexistente | Acuerdo con corpus |
| 2026-11-14 | Relaciones nativas solo con estado `hypothesis`; `unknown/conflict` bajan cobertura | Evitar fabricar uniones visualmente indeterminadas | Coordinación con cierre_montaje |
| 2026-11-14 | `structural_signature` define familia de partición | `product_family` puede aparecer en desarrollo y holdout sin fuga estructural | Coordinación con cierre_corpus |

## Dependencias / avisos

- Necesito de: fixtures privados del agente corpus para integración posterior; mis pruebas usarán fixtures propios.
- Afecta a: harness de evaluación offline y cierre reproducible.
- Aviso realizado: contrato enviado y aprobado por `/root/cierre_corpus`; `/root` informado del inicio.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| Focal semántica | `python -m pytest -q tests/test_semantic_evaluation.py` | 18 passed | Fixtures propios; sintéticos |
| Lint | `python -m ruff check evaluation/semantic.py tools/evaluate_semantic.py tests/test_semantic_evaluation.py` | All checks passed | Solo alcance propio |
| Integridad diff | `git diff --check -- evaluation/semantic.py tools/evaluate_semantic.py tests/test_semantic_evaluation.py docs/EVALUACION_SEMANTICA.md team/agente_cierre_semantica.md` | exit 0 | Worktree compartido con cambios ajenos |
| CLI pareado real | `python -m tools.evaluate_semantic --paired-output .runtime/poc-closure-benchmark/dev-smoke-v1 --output .runtime/poc-closure-benchmark/dev-smoke-semantic-v1` | baseline y final escritos; 1/1 casos conservados | No se abrió referencia privada |

## Bloqueos y cierre

- Bloqueos: ninguno.
- Pendientes: sellado privado y evaluación del benchmark a cargo de root/corpus tras freeze.
- Reservas liberadas: `evaluation/semantic.py`, `tools/evaluate_semantic.py`, `tests/test_semantic_evaluation.py` y `docs/EVALUACION_SEMANTICA.md` al entregar.
- Entrega: `/root`, con contrato, comandos, evidencia y límites.
