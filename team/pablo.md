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
- Estado: terminado (backend, API y tests); interfaz pendiente
- Rama: `feat/precedentes-persona2`, fusionada en `embeddings` (rama compartida con el nivel 1 de `team/sergio.md`) a petición del usuario

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
- Seis implementadores en paralelo con archivos disjuntos; paquete `backend/app/precedentes/` con las 12 ideas (commit `1fa4aad`).
- Routers registrados en `main.py` (`_incluir_routers_precedentes`) y prefijo `/api/v1/precedentes` añadido a la lista de funciones privadas del middleware: 403 en acceso público.
- Revisión independiente en solo lectura: 2 hallazgos altos (coste cúbico en 2.4, suplantación de actor en 3.4), 6 medios y 7 bajos. Todos corregidos por su implementador y verificados (segundo commit).
- Documentación del incremento en `docs/PRECEDENTES.md`.
- Fusión en `origin/embeddings` sobre el nivel 1 de Sergio, sin conflictos de texto. Integración semántica: umbrales calibrados de 1.2 en 2.1 (score relativo al techo de la consulta) y 2.3 (umbral combinado y abstención), coseno unificado de 1.4 en 3.3.

## Bloque 2 (2026-11-14): similitud y evaluación — terminado, integrado en `feat/similitud-evaluacion`

- Resultado: las cuatro ramas revisadas por Opus (1–3 rondas cada una) e integradas. Suite Python: 1198 passed, 1 skip; los mismos 2 fallos (`test_explorer_models.py`, falta `joblib`) y 6 errores de colección (dependencias opcionales del laboratorio, p. ej. `scipy`) que la línea base. Frontend sin cambios (no se ejecutó `npm test`).
- Enganches en `backend/app/main.py`: import de `precedentes.mantenimiento`, `ColaMantenimiento` en el `lifespan` y `tras_guardar_biblioteca(...)` tras `save_library_item` en `save_to_library`.
- `.gitignore`: añade `.claude/worktrees/`.
- Pendientes conocidos (no corregidos por falta de presupuesto):
  - Corpus, media: `_agrupar_cliques` deja casi duplicados dentro de una misma partición (representante de un grupo nuevo a ≤ tolerancia de otro representante). Corregir aplicando la misma regla que entre particiones a los supervivientes de la partición actual.
  - Corpus, baja: traslación independiente por vista en variantes (puede solapar vistas; usar un desplazamiento común). La tarea de identidad sigue siendo fácil para métodos que normalicen coordenadas: documentarlo.
  - Mantenimiento: sin escritura condicional en el repositorio (ventana mínima entre relectura y guardado); sin cola persistente; verificación de huella no programada.
  - Comparativa: B/C/D sin adaptador de proveedor real (lo lleva quien lleva el harness); D sin índice histórico anotado; la variante A apenas extrae tableros en vistas montadas de PlankAssembly (tableros que se tocan se fusionan): requiere extractor en `geometria/`.
  - Dataset PlankAssembly no descargado en esta máquina: el corpus solo se ha probado con fixtures sintéticos.

- Pedido por el usuario: "Lanza lo que no esté hecho ya" de las opciones 3, 4, 6 y 7 tras comprobar que 2.4, 3.1, 2.5/2.6 y 2.7 ya existían. Subagentes Sonnet en worktrees propios + revisor Opus en solo lectura.
- Rama de integración: `feat/similitud-evaluacion` (desde `embeddings`, con `main` fusionado). Ramas por agente: `feat/sim-nesting`, `feat/sim-mantenimiento`, `feat/sim-corpus`, `feat/sim-comparativa`.
- Tareas:
  - **Nesting real (3.1):** colocación por guillotina en `backend/app/precedentes/lotes.py` (+ módulo nuevo en `precedentes/`).
  - **Mantenimiento automático (2.5/2.6):** regeneración tras guardar revisión, huella del espacio por modelo/dimensiones/descriptor y candado persistente en SQLite; sin tocar `contratos/`.
  - **Corpus PlankAssembly + juicios reales (2.7/T11):** ampliar `tools/prepare_plankassembly.py`, generar juicios en `evaluation/recuperacion/`. Dataset aún no descargado: fixtures sintéticos.
  - **Comparativa de métodos (T13, `docs/COMPARATIVA_METODOS.md`):** módulo nuevo en `tools/`/`evaluation/`; el harness solo se invoca, no se modifica; sin llamadas de pago.
- Alcance ampliado: `tools/prepare_plankassembly.py`, `tools/comparativa_metodos*.py`, `evaluation/comparativa/`, `evaluation/recuperacion/`, sus tests en `tests/` y `backend/tests/`, y el punto de enganche mínimo tras guardar en biblioteca (se anota la ruta exacta al integrar).
- Fuera de alcance (compañeros): harness CAD (`agente/`, `general_furniture/`), `frontend/`, `contratos/`.

## Siguiente bloque

- Interfaz de usuario de los endpoints (coordinar con frontend).
- Generar el archivo de calibración real con `tools/calibrate_similarity.py` cuando haya biblioteca representativa.
- Promover a `contratos/` los modelos que se consoliden (acuerdo A/B).

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Modelos Pydantic nuevos en `backend/app/precedentes/`, no en `contratos/` | El usuario permite romper contratos y pide "lo que sea mejor"; aislarlos evita romper consumidores y permite promoverlos después con acuerdo A/B | Respuesta del usuario en sesión |
| 2026-11-14 | Herrajes (3.5) en tabla propia, sin añadir campos a `HistoricalRecord` | Cambiar `HistoricalRecord` alteraría `payload_hash` de registros existentes e invalidaría la caché de embeddings | Análisis de `historico/real_service.py` |
| 2026-11-14 | 3.5 solo como mecanismo, con datos sintéticos declarados | No existe histórico de herrajes | Respuesta del usuario en sesión |

## Dependencias / avisos

- Uso de Sergio (`team/sergio.md`): `similarity.thresholds` (1.2) y `similarity.math_utils` (1.4), solo lectura; no se modifican sus archivos.
- Solape potencial con el compañero: sus ideas 1.2–1.4 tocan `backend/app/similarity/`. El score híbrido (2.3) vive en `precedentes/` y solo llama a funciones públicas de `similarity/`, sin modificarlas.
- Afecta a: `agente_historico_real` (se lee `HistoricalStore` sin modificarlo); frontend (los endpoints nuevos no tienen interfaz todavía).
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Línea base antes de cambios | `pytest -q -p no:cacheprovider --continue-on-collection-errors backend/tests tests` | 825 pasan, 1 skip, 2 fallan, 6 errores de colección | Fallos previos: `test_explorer_models.py::test_training_numeric_artifact_uses_only_train_and_preserves_sklearn_prediction[knn|logreg]`. Errores de colección (dependencias opcionales del laboratorio): `tests/test_reconstruction3d_evaluation.py`, `tests/test_semantic_lab_{classifier_comparison,components,evaluate,jev_comparison,probe_datasets}.py` |

| Tras implementación y correcciones | mismo comando | 984 pasan, 1 skip, los mismos 2 fallos y 6 errores de colección de la línea base | Sin regresiones; 159 tests nuevos |
| Lint del código nuevo | `ruff check backend/app/precedentes backend/tests/test_precedentes_*.py tools/evaluar_recuperacion.py` | limpio | `main.py` conserva sus 20 avisos previos; no se añade ninguno |
| Bloqueo en acceso público | `pytest backend/tests/test_precedentes_integracion.py` | 3 pasan | Comprueba 403 en las 18 rutas |

## Bloqueos y cierre

- Bloqueos: ninguno
- Pendientes: interfaz de usuario de los cinco endpoints
