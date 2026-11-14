# Pablo — coordinación de trabajo

## Identidad y autorización

- Nombre declarado por el usuario: Pablo
- Rol: Persona 2 del reparto de `docs/BRAINSTORMING_EMBEDDINGS.md` (funcionalidades que consumen la similitud)
- Archivo creado o designado explícitamente: el usuario indicó "la mía es pablo" el 2026-11-14 al pedir la implementación
- Última actualización: 2026-11-14

## Tarea de la sesión

- Objetivo concreto: implementar con subagentes y un revisor las ideas **2.1 a 3.5** de `docs/BRAINSTORMING_EMBEDDINGS.md` (12 ideas, backend + API + tests, sin interfaz):
  - 2.1 Sugerencias de valores que faltan · 2.2 Presupuesto por analogía · 2.3 Score híbrido · 2.4 Piezas casi idénticas · 2.5 Regeneración de embeddings · 2.6 Versionado del espacio · 2.7 Evaluación de recuperación
  - 3.1 Lotes de corte · 3.2 Búsqueda en lenguaje natural · 3.3 Embeddings de imagen (mecanismo) · 3.4 Aprendizaje de decisiones (mecanismo) · 3.5 Herrajes y mecanizados (mecanismo, datos sintéticos)
- Las ideas 1.1–1.7 quedan para el compañero (corrección del usuario: "nosotros hacemos del 2.1 para adelante").
- Referencia del plan: `docs/BRAINSTORMING_EMBEDDINGS.md`, secciones 2.2, 2.4, 3.1, 3.2, 3.5
- Estado: en curso
- Rama: `feat/precedentes-persona2`

## Alcance y reservas

- Archivos o carpetas que puedo editar:
  - `backend/app/precedentes/` (paquete nuevo)
  - `backend/tests/test_precedentes_*.py`
  - `tools/evaluar_recuperacion.py` y `evaluation/recuperacion/` (2.7)
  - `backend/app/main.py`: solo el registro de los routers de `precedentes`
  - `docs/PRECEDENTES.md` (documentación del incremento)
  - este archivo
- Dependencias que solo leeré: `backend/app/historico/`, `backend/app/semantic/`, `backend/app/similarity/`, `backend/app/agente/provider.py`, `backend/app/contratos/modelos.py`, `backend/app/servicios/repository.py`
- Archivos compartidos que requieren coordinación: `backend/app/main.py` (registro de routers, una sola zona)
- Solapes detectados y acuerdo para resolverlos: no se modifica `historico/` (propiedad de `agente_historico_real`) ni `contratos/`; los modelos nuevos viven en `precedentes/`.

## Hecho en el último bloque

- Brainstorming ampliado y publicado en `main` (`c66f93b`).
- Creado este archivo y la rama `feat/precedentes-persona2`.

## Siguiente bloque

- Implementación paralela por subagentes, revisión independiente, integración en `main.py` y verificación completa.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Modelos Pydantic nuevos en `backend/app/precedentes/`, no en `contratos/` | El usuario permite romper contratos y pide "lo que sea mejor"; aislarlos evita romper consumidores y permite promoverlos después con acuerdo A/B | Respuesta del usuario en sesión |
| 2026-11-14 | Herrajes (3.5) en tabla propia, sin añadir campos a `HistoricalRecord` | Cambiar `HistoricalRecord` alteraría `payload_hash` de registros existentes e invalidaría la caché de embeddings | Análisis de `historico/real_service.py` |
| 2026-11-14 | 3.5 solo como mecanismo, con datos sintéticos declarados | No existe histórico de herrajes | Respuesta del usuario en sesión |

## Dependencias / avisos

- Necesito de: compañero (1.1 medición y 1.2 umbrales calibrados) para afinar umbrales; mientras tanto se usan umbrales explícitos y configurables.
- Solape potencial con el compañero: sus ideas 1.2–1.4 tocan `backend/app/similarity/`. El score híbrido (2.3) vive en `precedentes/` y solo llama a funciones públicas de `similarity/`, sin modificarlas.
- Afecta a: `agente_historico_real` (se lee `HistoricalStore` sin modificarlo); frontend (los endpoints nuevos no tienen interfaz todavía).
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Línea base antes de cambios | `pytest -q -p no:cacheprovider --continue-on-collection-errors backend/tests tests` | 825 pasan, 1 skip, 2 fallan, 6 errores de colección | Fallos previos: `test_explorer_models.py::test_training_numeric_artifact_uses_only_train_and_preserves_sklearn_prediction[knn|logreg]`. Errores de colección (dependencias opcionales del laboratorio): `tests/test_reconstruction3d_evaluation.py`, `tests/test_semantic_lab_{classifier_comparison,components,evaluate,jev_comparison,probe_datasets}.py` |

## Bloqueos y cierre

- Bloqueos: ninguno
- Pendientes: interfaz de usuario de los cinco endpoints
