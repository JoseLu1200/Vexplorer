# Agente PR2 similitud — coordinación de trabajo

## Identidad y autorización

- Nombre declarado por el usuario: Agente PR2 similitud (IA, GPT-6.1 Sol)
- Rol: revisión e implementación focalizada de nivel 1
- Archivo creado o designado explícitamente: el usuario autorizó registros `team/agente_pr2_*.md`; coordinación asignó este alcance el 2026-11-14
- Última actualización: 2026-11-14

## Tarea de la sesión

- Objetivo concreto: corregir export de calibración compatible con runtime, coseno estable compartido, validación de matrices normalizadas y pandeo conservador.
- Referencia del plan: `docs/BRAINSTORMING_EMBEDDINGS.md`, ideas 1.1, 1.4 y 1.6.
- Estado: en curso.

## Alcance y reservas

- Archivos o carpetas que puedo editar: `tools/calibrate_similarity.py`, `backend/app/similarity/math_utils.py`, `backend/app/validador/plausibilidad.py`, sus pruebas correspondientes y este registro.
- Dependencias que solo leeré: `backend/app/agente/runner.py`, contratos, catálogo y documentación.
- Archivos compartidos que requieren coordinación: ninguno fuera del alcance asignado.
- Solapes detectados y acuerdo para resolverlos: alcance asignado explícitamente por coordinación; no se editará `runner.py` sin aprobación adicional.

## Hecho en el último bloque

- Revisión reproducible completada; cuatro defectos confirmados.

## Siguiente bloque

- Ciclos TDD rojo-verde para calibración, matemáticas y pandeo.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | No cablear aún pandeo en `runner.py` | Falta acordar el punto con piezas disponibles y trazables | Instrucción de coordinación |

## Dependencias / avisos

- Necesito de: coordinación para aprobar el hook de producción de pandeo.
- Afecta a: umbrales runtime, explorador semántico y validador.
- Aviso realizado: hallazgos y reproducciones enviados a coordinación.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Baseline focalizado | `python -m pytest -q backend/tests/test_similarity_unified.py backend/tests/test_similarity_clustering.py backend/tests/test_similarity_abstention.py backend/tests/test_validador_pandeo.py tests/test_calibrate_similarity.py` | 54 pasan | Antes de correcciones |

## Bloqueos y cierre

- Bloqueos: ninguno para el alcance asignado.
- Pendientes: propuesta exacta del hook de producción; implementación y verificación.
- Reservas liberadas: no aplica todavía.
- Entrega a otra persona: coordinación integrará sin commits de este agente.
