# Agente de evaluación de similitud

## Identidad y autorización

- Identidad: agente de IA `similarity_evaluation`; no representa a una persona.
- Autorización: delegación explícita de `/root` dentro del swarm solicitado por el usuario el 2026-11-14.

## Alcance y reservas

- Propiedad exclusiva: `evaluation/similarity_regression.py`, `tests/test_similarity_regression.py`, `docs/SIMILITUD_EVALUACION.md` y este registro.
- Solo lectura: backend, modelos, servicios, API, frontend, benchmarks y artefactos existentes.
- No reutilizar respuestas privadas u ocultas; los casos y relevancias son fixtures sintéticos propios.
- No hacer commits ni modificar archivos sucios ajenos.

## Tarea

Construir una evaluación offline reproducible para defectos de similitud: familias distintas, negativos duros de geometría igual con material/acabado diferente, cambio de grosor 18→36 (incluido 864→828), variantes dimensionales, equivalencia bajo reordenamiento/IDs, ranking con duplicados y agrupación no transitiva. Separar explícitamente evidencia geométrica de la frontera semántica simulada y no presentar mocks como validación empresarial o ranking real de embeddings.

## Dependencias y avisos

- Coordinación solicitada a `/root/similarity_backend` para las firmas de ranking y agrupación.
- Coordinación solicitada a `/root/library_api` para helpers/payloads de biblioteca.
- Cualquier embedding real local disponible se inspeccionará solo en lectura y su procedencia se documentará; no es requisito para aprobar la evaluación sintética.

## Estado

- Evaluador, pruebas y documentación implementados con fixtures propios; verificación focal final verde.
- Suite global ejecutada: 686 aprobadas y 2 fallos ajenos en archivos concurrentes de tabla y contexto live; ambos se registran sin atribuirlos a esta entrega.

## Registro

- 2026-11-14: alcance registrado antes de editar pruebas o implementación; no se detectó solape sobre los cuatro archivos reservados.
- 2026-11-14: RED observado: `python -m pytest tests/test_similarity_regression.py -q` falló al importar el módulo inexistente.
- 2026-11-14: coordinadas firmas con similitud y API: comparación técnica, clave canónica, deduplicación, reranking semántico y complete-link; cross-version se excluye.
- 2026-11-14: GREEN focal: 9 pruebas aprobadas. La ejecución CLI midió antes/después en los mismos 8 registros: top-1 falso→verdadero, reciprocal rank 1/3→1, recall único@5 1/3→1 y duplicación@5 0,4→0.
- 2026-11-14: frontera semántica sintética declarada: negativo duro coseno 0,999546 frente a equivalente 0,999; el reranking técnico invierte el orden. No se usaron embeddings reales, red, respuestas ocultas ni validación empresarial.
- 2026-11-14: tras cierre de firmas del motor, `python -m pytest tests/test_similarity_regression.py backend/tests/test_similarity_technical.py backend/tests/test_backend_embeddings.py backend/tests/test_backend_library_api.py -q` → 34 passed; `ruff` y `git diff --check` correctos.
- 2026-11-14: suite global `python -m pytest -q` → 686 passed, 2 failed: `test_table_baseline_run_review_and_partial_cost_are_revision_bound` (`estimate` no recargado) y `test_vector_context_announces_typed_assembly_and_exact_document_references` (falta `reference_authority`). Ninguno toca los cuatro archivos propios.
