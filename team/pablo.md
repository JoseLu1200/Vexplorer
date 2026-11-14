# pablo — coordinación de trabajo

## Identidad y autorización

- Nombre declarado por el usuario: pablo
- Rol: persona usuaria del repositorio; trabaja con una sesión de Claude. No ocupa de forma permanente el rol A, B, C ni D; las transferencias puntuales de abajo se registran aquí.
- Archivo creado o designado explícitamente: el usuario pidió "Crea uno para mi, \"pablo\"" el 2026-11-14.
- Última actualización: 2026-11-14

## Tarea de la sesión

- Objetivo concreto: mejoras específicas de CAD y del harness derivadas de la investigación de la sesión, en la rama `mejoras/cad-harness` para comprobar el merge después.
- Referencia del plan: T1 (extracción geométrica), T11 (propuestas desde planos pobres) y exportación de [CASO_DE_USO_Y_EVALUACION](../docs/CASO_DE_USO_Y_EVALUACION.md).
- Estado: tres bloques implementados y verificados con pytest (178 pruebas). Bloques 1 y 2 en commits subidos; bloque 3 sin commit. Pendiente de revisión y merge.

## Alcance y reservas

- Ampliación del 2026-11-14 (tercer bloque), por petición del usuario: "Dale, aplicalos", sobre la lista de mejoras propuesta en la sesión:
  - `pyproject.toml` (raíz, compartido): solo `package-data` del catálogo y `ruff` como extra de desarrollo
  - `backend/app/validador/` (comprobación de cotas apoyadas en geometría), `backend/app/servicios/decomposition.py` (evidencia de taladros en laterales)
  - pruebas nuevas `backend/tests/test_tercer_bloque.py`, `backend/tests/test_replay_y_comparacion.py`
  - tras la respuesta "Aplicar las dos": `backend/app/contratos/modelos.py` (`RunSnapshot.mode` y `CompareCandidatesArgs`), nuevos `backend/app/agente/replay.py` y `backend/app/agente/comparacion.py`
  - Fuera de alcance: `frontend/` (C) y datos reales del taller. Cambios de `contratos/` (replay grabado y `comparar_candidatas`) solo tras preguntar.
- Ampliación del 2026-11-14 (segunda sesión), por petición del usuario: "Pues aplica todos los cambios, soy pablo", tras leer [INVESTIGACION_ALIMENTACION_HARNESS](../docs/INVESTIGACION_ALIMENTACION_HARNESS.md) y el aviso de que el canal visual requiere acuerdo A/B:
  - `backend/app/agente/config.py`, `backend/app/agente/provider.py`, `backend/app/agente/tools.py`, nuevo `backend/app/agente/vision.py`; `backend/app/main.py` ya estaba en el alcance
  - paquete nuevo `backend/app/validador/` (plausibilidad con catálogo del taller)
  - `backend/app/contratos/modelos.py`: solo el modelo de argumentos de la herramienta visual, aditivo y desactivado por defecto
  - pruebas nuevas `backend/tests/test_ingesta_ampliada.py`, `test_agente_contexto.py`, `test_validador_plausibilidad.py`, `test_agente_vision.py`
  - `docs/INVESTIGACION_ALIMENTACION_HARNESS.md`
  - Fuera de alcance: `tests/test_demo_*` (D) y `frontend/` (C). Si una prueba de D falla, se para y se informa.
- Archivos o carpetas que puedo editar (ampliado el 2026-11-14 por petición del usuario: "cambia todo lo necesario para que el sistema mejore"):
  - `backend/app/contratos/modelos.py` (solo campos opcionales con valor por defecto)
  - `backend/app/ingesta/dxf_reader.py`, `backend/app/geometria/extraction.py`, `backend/app/servicios/decomposition.py`, `backend/app/servicios/repository.py`
  - `backend/app/agente/runner.py`, `backend/app/agente/prompts.py`
  - `backend/app/salida/service.py`, `backend/app/main.py`
  - `backend/tests/test_backend_agent.py` (aserciones ajustadas al nuevo comportamiento) y pruebas nuevas `test_view_detection.py`, `test_cutlist_export.py`, `test_observed_thickness_linetype.py`
  - `docs/MEJORAS_CAD.md` y este archivo
- Dependencias que solo leeré: `evaluation/` (no se abren las referencias reservadas), `data/planos_demo/`, `frontend/`.
- Archivos compartidos que requieren coordinación: `contratos/` y `agente/` (B), `geometria/`, `ingesta/` y `decomposition.py` (A), `tests/test_demo_*` (D, sin modificar), `frontend/` (C, sin modificar).
- Solapes detectados y acuerdo para resolverlos: con A y B por las rutas anteriores, cuyos registros declaran su trabajo como completado. No se les ha avisado: el merge de la rama es el punto de revisión.

## Hecho en el último bloque

- Vistas sin etiqueta por alineación; tipo de línea en el ledger; espesor observado de laterales; veta y cantos por pieza; lista de corte CSV; contexto del agente con resumen del ledger e IDs válidos en los errores.
- Documentación en `docs/MEJORAS_CAD.md`.

## Hecho en el segundo bloque

- Ingesta: bloques anidados y MINSERT con IDs trazables, atributos, círculos, arcos, bulges, POLYLINE 2D, elipses, splines, tramas, cotas por ordenadas, paperspace, recuperación de DXF dañados y pista de unidades.
- Geometría: filas de taladros como evidencia; contornos también desde POLYLINE 2D.
- Validador nuevo `validador/plausibilidad.py` con catálogo del taller (solo Sistema 32 verificado).
- Agente: agregados, truncado explícito, plausibilidad en el contexto; `max_output_tokens` configurable; canal visual Set-of-Mark opcional.
- Documentación: `docs/MEJORAS_CAD.md` (segundo bloque) y `docs/INVESTIGACION_ALIMENTACION_HARNESS.md`.

## Siguiente bloque

- Revisión del merge por A y B (contrato y geometría) y por D (efecto en el E2E).
- C: botón de lista de corte, campos de veta/cantos y precarga del espesor observado en la revisión.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Cambiar `contratos/` solo con campos opcionales y valor por defecto | El usuario autorizó el cambio ("cambia todo lo necesario"); aditivo para no invalidar resultados guardados; `schema_version` sin cambios | Mensaje del usuario del 2026-11-14. No hay acuerdo de A/B ni aviso a C/D: se delega en la revisión del merge |
| 2026-11-14 | `thickness_mm` sigue `None`; el espesor medido va en `observed_thickness_mm` | Distinguir observación de confirmación; mantiene las aserciones de `tests/test_demo_e2e.py` | `docs/MEJORAS_CAD.md` |
| 2026-11-14 | No ampliar el descriptor, ni la cadena de costes, ni usar `linetype` en reglas geométricas | Rompería embeddings guardados / faltan tarifas / falta caso de calibración | `docs/MEJORAS_CAD.md` |
| 2026-11-14 | Bloques, filas de taladros y tramas como `Evidence` de tipo `geometry`, sin campos nuevos en `DrawingEntity` | Evita otro cambio de contrato; la evidencia ya es trazable a entidades | `docs/MEJORAS_CAD.md` |
| 2026-11-14 | Las aproximaciones (`approximated_*`), DXF recuperados y contenido en paperspace dejan `needs_review`; las entidades leídas de forma exacta (CIRCLE, ARC, INSERT expandido) sí pueden dar `ready` | Una aproximación o un archivo reparado no debe pasar por lectura limpia; una lectura exacta no tiene por qué bloquear | `extraction.py` `REVIEW_WARNING_PREFIXES` |
| 2026-11-14 | Catálogo por defecto solo con Sistema 32 (Ø5, paso 32, retranqueo 37); espesores y cantos vacíos | Únicos valores confirmados en la investigación; el resto lo aporta compras | `validador/catalogo_taller.json` |
| 2026-11-14 | `VisualizeViewArgs` en `contratos/` y canal visual desactivado por defecto | El usuario pidió "aplica todos los cambios" tras el aviso de que requería acuerdo A/B; se limita a un modelo aditivo detrás de `VEXPLORER_AGENT_VISION` | Mensaje del usuario del 2026-11-14. Sin acuerdo de A/B ni aviso a C/D |
| 2026-11-14 | `max_output_tokens` por defecto 4096 | 1200 es frágil con modelos de razonamiento; configurable con `OPENAI_MAX_OUTPUT_TOKENS` | `agente/config.py` |
| 2026-11-14 | `RunSnapshot.mode` con `recorded_replay` y `CompareCandidatesArgs` | El usuario eligió "Aplicar las dos" tras la pregunta que indicaba que la regla 7 exige acuerdo A/B | Respuesta del usuario del 2026-11-14. Sin acuerdo de A/B ni aviso a C/D |
| 2026-11-14 | Replay indexado por huella de lo que vio el modelo, sin grabaciones sintéticas en el repo | Una grabación solo es fiel si el contexto es idéntico; inventar una sería simular actividad (HARNESS.md) | `agente/replay.py` |
| 2026-11-14 | Entorno `.venv` local con `pip install -e ".[test]"` | Solo dependencias ya declaradas en `pyproject.toml`; `.venv` está ignorado por git | `git check-ignore .venv` |

## Dependencias / avisos

- Necesito de: A y B para validar los cambios de contrato y geometría; D para confirmar el E2E.
- Afecta a: C (campos nuevos y endpoint `format=cutlist` sin interfaz; nuevos tipos de entidad CIRCLE, ARC, HATCH, ELLIPSE, SPLINE, POLYLINE, ATTRIB que el visor dibuja como polilíneas; las cotas por ordenadas no tienen gráfico). A (ingesta y geometría ampliadas). B (contexto, proveedor, herramienta visual y `VisualizeViewArgs`). D (sin cambios en `tests/test_demo_*`, que siguen pasando).
- Aviso realizado: ninguno a A/B/C/D; se informa al usuario en el informe de la sesión.
- Cambio de `contratos/` en el tercer bloque: `RunSnapshot.mode` admite `recorded_replay` y `CompareCandidatesArgs`; afecta a C (el frontend ya contempla `recorded_replay`).
- Cambio de `contratos/`: sí, aditivo (`DrawingEntity.linetype`, `ComponentProposal.observed_thickness_mm` y `thickness_source_entity_ids`, `ReviewDecision` y `ResolvedPiece` con `grain` y `edge_banding`). Autorizado por el usuario; sin acuerdo explícito de A y B.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Línea base (rama `main`) | `.venv/Scripts/python.exe -m pytest -q` | 119 passed | Python 3.12 (el equipo documentó 3.14) |
| Detección de vistas | `pytest backend/tests/test_view_detection.py -q` | 6 passed; con el `extraction.py` original fallan las 3 de inferencia | Solo fixture propio y dibujos mínimos |
| Suite completa tras los cambios | `.venv/Scripts/python.exe -m pytest -q` | 140 passed | Sin pruebas de JavaScript ni navegador (no hay Node en este equipo) |
| Segundo bloque: ingesta, validador, contexto, visión | `.venv/Scripts/python.exe -m pytest -q` | 166 passed (26 nuevas en `test_ingesta_ampliada.py`, `test_validador_plausibilidad.py`, `test_agente_contexto.py`, `test_agente_vision.py`) | Planos sintéticos; ningún DWG real de taller |
| Planos de demo tras el segundo bloque | extracción de `data/planos_demo/*.dxf` | Mismo estado (`ready` salvo unidades desconocidas), sin avisos nuevos salvo `unit_hint_measurement:metric` en el de unidades desconocidas | — |
| Tercer bloque | `.venv/Scripts/python.exe -m pytest -q` | 178 passed (6 en `test_tercer_bloque.py`, 6 en `test_replay_y_comparacion.py`) | Sin DWG real; sin frontend; grabación y replay solo con proveedor simulado |
| Regresión de demos en el tercer bloque | JSON de `extract_drawing` y escenarios de `data/planos_demo/*.dxf` antes y después | Idéntico | — |
| Rendimiento | plano sintético de 25 000 líneas en 1 000 INSERT | 309 s → 1,1 s | Medición única en este equipo |
| Lint | `ruff check` sobre archivos creados en la rama | limpio | Archivos preexistentes con avisos de estilo previos, sin tocar |
| Proveedor real | no ejecutado | pendiente | Ni el contexto nuevo ni `input_image` se probaron contra la API; solo `httpx.MockTransport` y proveedor falso |

## Bloqueos y cierre

- Bloqueos: ninguno.
- Pendientes: ver `docs/MEJORAS_CAD.md`, sección "No aplicado y por qué".
- Reservas liberadas: ninguna aún.
- Entrega a otra persona: rama `mejoras/cad-harness`, pendiente de revisión y merge.
