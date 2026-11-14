# Agente de evaluación integral — métricas independientes

## Identidad y autorización

- Identidad: agente de IA de evaluación integral; no representa a una persona.
- Autorización: delegación explícita del coordinador dentro del swarm renovado por el usuario el 2026-11-14.
- Rol: ampliar la evaluación reproducible sin exponer referencias privadas al runtime.

## Tarea y alcance

- Objetivo: ingerir predicciones congeladas y referencias independientes por separado; medir BOM/dimensiones, relevancia de recuperación, error de coste/horas y tiempos técnico-vs-asistido con cobertura y lenguaje honesto.
- Propiedad: nuevo módulo `evaluation/metrics.py`, nuevo CLI `tools/evaluate_cases.py`, pruebas nuevas `tests/test_evaluation_metrics.py`, documentación nueva `docs/EVALUACION_INTEGRAL.md`, `evaluation/__init__.py`, adición de empaquetado `evaluation*` en `pyproject.toml`, este registro y artefactos temporales ignorados bajo `.runtime/`.
- Transferencia adicional autorizada por backend general: nuevos `backend/app/general_furniture/drawing_renderer.py` y `backend/tests/test_general_furniture_drawing_renderer.py`; no editar `derivations.py`.
- Ampliación de auditoría autorizada: nuevo `docs/DATASETS_INTEGRALES.md` y preparación local fuera de Git `../plankassembly_adapter_test_v1{,_private}`; sin inferencia ni redistribución.
- Cohorte autónoma autorizada: `../plankassembly_adapter_blind20_v2{,_private}`, extensión offset/limit del preparador y métricas ortogonales de estado factual/revisión automática; referencia privada no abierta antes del freeze.
- Solo lectura: backend, contratos, fixtures/referencias existentes y documentación compartida.
- No se modificará `evaluation/reference/` ni se introducirá ninguna ruta privada en backend, proveedor, prompts, herramientas o índice histórico.
- Los fixtures autocontenidos son validación de desarrollo, nunca benchmark independiente o ciego.

## Estado

- Módulo, CLI y documentación implementados por TDD; pendiente puntuar las seis salidas PlankAssembly que congelará el coordinador sin leer referencias privadas.

## Hecho

- Implementado informe agregado determinista para BOM por tipo/cantidad, dimensiones, relevancia top-k, coste, horas y tiempos pareados.
- Añadidas abstenciones de cantidad, coste, horas, retrieval y tiempos con denominadores/cobertura; el error relativo omite referencias cero.
- Añadida alineación privada uno-a-uno posterior al freeze para no entregar claves del oráculo al sistema.
- Añadidos controles de partición por proyecto/familia y detección/exclusión de comparables del mismo proyecto, familia o grupo duplicado.
- El informe no contiene rutas ni filas privadas; el evaluador permanece fuera de FastAPI y frontend.
- Empaquetado `evaluation*` para que el CLI instalado resuelva su import.
- Entregado renderer general disjunto SVG/DXF con unidades mm, anotaciones L/W/T/Q/estado/fuente y un rectángulo por ocurrencia conocida; backend general integra el helper.
- Puntuada la pasada live PlankAssembly v4 solo después de congelar seis respuestas públicas: 33/36 tipos alineados por dimensiones, 99/108 campos comparados, pero todas las dimensiones son hipótesis y todas las cantidades siguen desconocidas.
- Inventariados Cadblock, corpus mecánico, tres generaciones del piloto, PlankAssembly y adaptadores. Preparados diez casos adicionales del split oficial `test`, sin solape con los seis `valid`, y tres rutas Cadblock de mobiliario admitidas solo para robustez sin oráculo BOM.
- Puntuadas las diez ejecuciones live nuevas después de congelarlas: 77/77 tipos de referencia alineados dimensionalmente entre 88 propuestas; 231/231 campos hipótesis comparados; cantidad desconocida en todos los tipos y 0/96 ocurrencias recuperadas.
- Preparada cohorte ciega de 20 casos nuevos del split test (offset 10) para ensayo pareado primer borrador→crítico, con ZIP individual endurecido y sin split/family hash/BOM/textos/rutas privadas.
- El evaluador separa ahora certeza (`hypothesis`, `confirmed`, etc.) de proceso (`unreviewed`, `auto_reviewed`, `human_reviewed`) para dimensiones, cantidades/ocurrencias y escenarios; auto-review nunca promueve verdad.

## Decisiones

- Predicciones y referencias se cargan desde ficheros distintos; el CLI abre la referencia solo en el proceso evaluador.
- Las métricas publican numerador, denominador y cobertura, y omiten error relativo cuando la referencia es cero o desconocida.
- El informe puede describir una diferencia temporal pareada, pero no la denomina ahorro ni extrapola utilidad causal.
- Ningún dato empresarial se fabrica; los ejemplos de pruebas quedan marcados como `developer_fixture`.

## Dependencias / avisos

- No hay cambios de contrato ni dependencias del runtime.
- El valor empresarial sigue bloqueado por planos, costes/horas, juicios de relevancia y sesiones cronometradas reales de técnicos.

## Verificación

- RED inicial: `python -m pytest tests/test_evaluation_metrics.py -q` falló en colección por ausencia de `evaluation.metrics`.
- RED de alineación/abstención: 3 fallos esperados por claves privadas/locales distintas, shape de dataset y cantidad `null`.
- GREEN focal final: `.venv\Scripts\python.exe -m pytest tests/test_evaluation_metrics.py -q` → `9 passed`.
- Renderer focal: `.venv\Scripts\python.exe -m pytest backend/tests/test_general_furniture_drawing_renderer.py -q` → `2 passed`.
- Focal combinado evaluador+renderer: `11 passed` antes del último control de estado dimensional; evaluador final repitió `9 passed`.
- Preparador PlankAssembly tras la nueva generación: `.venv\Scripts\python.exe -m pytest tests/test_prepare_plankassembly.py -q` → `2 passed`; hashes públicos/privados nuevos → 0 discrepancias.
- Evaluador+preparador tras estado ortogonal y offset 20: `12 passed`; auditoría pública blind20_v2 → 0 hallazgos y referencia privada no leída.
- Sintaxis: `.venv\Scripts\python.exe -m compileall -q evaluation tools/evaluate_cases.py` → sin salida.
- Wheel: `.venv\Scripts\python.exe -m pip wheel . --no-deps ...` → construido; contiene `evaluation/{__init__,metrics}.py` y `tools/evaluate_cases.py`.
- Diff: `git diff --check -- <rutas propias>` → sin salida.
- Ruff no disponible en el entorno: `No module named ruff`.
- Suite global fresca: `477 passed, 3 failed, 1 warning`; los tres fallos concurrentes ajenos son capability `general_furniture` aún false y firmas pendientes `HistoricalStore(max_records=...)` / `create_history_router(max_csv_bytes=...)`.
- Segunda suite global concurrente: `486 passed, 4 failed, 1 warning`; fallos ajenos en tres fixtures de revisión general tras hacer obligatorio `source_contour_ids` y capability general aún false.
- Revisión Astra incorporada: fingerprint SHA-256 de bytes exactos, correcciones, hipótesis falsas, preservación de escenarios ambiguos, compatibilidad económica y escritura atómica sin sobreescribir entradas.

## Evidencia externa pendiente

- Inspeccionados manifiestos locales del adaptador PlankAssembly: seis casos, cinco `development`, uno `holdout`, `inference_evaluated: false`, sin predicciones congeladas. No se redistribuyeron datos.
- El coordinador congeló las inferencias reales sobre los seis DXF públicos antes de que este evaluador las alineara contra la referencia privada; no se creó una baseline vacía ni se ajustó la propuesta al oráculo.
- El coordinador congeló v4 con seis ejecuciones live correctas y hashes. Resultado agregado: tipos P=0,868/R=0,917/F1=0,892; dimensiones hipótesis cobertura=0,917, MAE=0,202 mm, 97/99 dentro de 1 mm; cantidad cobertura 0 y recobrado de ocurrencias 0/54; escenarios alineados 0/6. Coste, horas, retrieval y tiempos sin denominador compatible. No se afirma benchmark ciego, identidad semántica ni ahorro.
- Test10 congelado: tipos P=0,875/R=1,000/F1=0,933; 11 hipótesis no alineadas; dimensiones hipótesis 231/231, MAE=0,719 mm, 229/231 dentro de 1 mm; cantidad 0/96; escenarios 0/10. Split development9 y holdout1 reportados por separado; un holdout no acredita generalización.
- Runner pareado rastreable: `tools/run_general_benchmark.py` acepta DXF públicos o ZIP estrictos, congela P1 antes del crítico, conserva fallos, registra hashes de fuente/PNG/código y exporta manifiestos evaluables baseline/final sin abrir oráculos. El manifest final enmascara a `null/unknown` campos no aceptados por el crítico y conserva escenarios provisionales no conflictivos aunque la revisión global sea incompleta. Pruebas offline en `tests/test_run_general_benchmark.py`.
- Blind20 congelado y puntuado tras verificar 192 archivos: baseline tipos F1=0,948, dimensiones 327/345 (317 a 1 mm), cantidad cobertura 104/115, F1=0,921 y 134/152 ocurrencias; final tipos F1=0,884, dimensiones 297/345 (287 a 1 mm), cantidad cobertura 98/115, F1=0,901 y 127/152 ocurrencias. Un fallo de proveedor cuenta con final vacío. Alineaciones por caso: 0 mejoran, 16 iguales, 4 bajan; 19 finales `incomplete` y cero reparaciones semánticas. La abstención dimensional impide matching y no equivale por sí sola a negar el componente. La elegibilidad por tripleta sin orientación conserva comparabilidad con test10; el MAE orientado (6,331/6,970 mm) expone intercambios de largo/ancho. Escenarios sin juicio semántico: 0/20 baseline y 0/19 final. Sin coste/horas/tiempos compatibles en esta cohorte y sin afirmación de ahorro.
- Alineación privada reproducible extraída a `tools/build_panel_evaluation_references.py`, sin rutas ni hashes del corpus. Pruebas independientes cubren redondeo/duplicados, permutación de ejes, abstención, máxima cardinalidad, mínimo error y binding SHA de un split. El CLI rastreable reprodujo exactamente los objetos baseline/final usados en blind20.
