# Agente de hallazgos — evaluación con técnicos

## Identidad y autorización

- Identidad: agente de IA `evaluation`; no representa a una persona ni a un técnico.
- Rol: evaluación offline y protocolo de recogida de evidencia.
- Archivo creado por autorización explícita del usuario transmitida por `/root` el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: implementar una colección y un scorer para sesiones manuales/asistidas, correcciones, piezas omitidas y error económico, sin fabricar evidencia humana.
- Estado: terminado dentro del alcance propio.

## Alcance y reservas

- Propiedad exclusiva: `evaluation/technician_study.py`, `tools/evaluate_technician_study.py`, `tests/test_technician_study_evaluation.py`, `docs/ESTUDIO_TECNICOS.md` y este registro.
- Artefactos de ejecución: `.runtime/evaluation-hallazgos/` (ignorado por Git).
- Solo lectura: evaluadores, predicciones y referencias existentes, datos públicos económicos y registros ajenos.
- No se modificará `evaluation/metrics.py`, reservado históricamente por `agente_evaluacion_integral`.
- Solapes detectados: ninguno en las rutas nuevas; el scorer general se reutiliza sin cambios.

## Hecho en el último bloque

- Implementado el scorer agregado con validación de procedencia, congelación, particiones, sesiones, correcciones, exclusiones y metadatos económicos.
- Implementado CLI con salida atómica que rechaza sobrescribir la entrada y no publica identificadores de filas.
- Documentado el protocolo, el contrato JSON y los límites de interpretación en `docs/ESTUDIO_TECNICOS.md`.
- Reproducidos Blind20 baseline/final y el score económico público LOPO en `.runtime/evaluation-hallazgos/`.

## Siguiente bloque

- Recoger datos autorizados de planos empresariales y sesiones observadas. El tooling queda listo; el repositorio no contiene esa evidencia.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-14 | Mantener el estudio en ficheros nuevos | Evitar solape y conservar el evaluador integral estable | Autorización de `/root` |
| 2026-11-14 | Informar diferencias manual/asistido como descriptivas | Sin asignación y observaciones humanas reales no hay soporte causal | Requisito de no fabricar evidencia |
| 2026-11-14 | Contar incompatibilidades económicas por caso y motivos por campo | Un caso puede diferir en más de un metadato | Regresión RED→GREEN |

## Dependencias / avisos

- Necesito de: datos empresariales autorizados y sesiones observadas para producir evidencia real.
- Afecta a: futuras evaluaciones, no al runtime ni a contratos del producto.
- Aviso realizado: `/root` recibió el inventario y el diseño de recogida.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| RED inicial | `.venv\Scripts\python.exe -m pytest tests/test_technician_study_evaluation.py -q` | Fallo en colección: módulo ausente | Fallo esperado antes de implementar |
| GREEN propio | mismo comando | `5 passed in 0.37s` | Fixtures de desarrollo, sin técnicos reales |
| Integración evaluación | `.venv\Scripts\python.exe -m pytest -q tests/test_technician_study_evaluation.py tests/test_evaluation_metrics.py tests/test_run_general_benchmark.py tests/test_build_panel_evaluation_references.py` | `37 passed in 1.87s` | Sin red ni proveedor |
| Estática | `python -m ruff check <rutas propias>` + `compileall` + `git diff --check` | Sin hallazgos, exit 0 | Alcance propio |
| Suite global | `.venv\Scripts\python.exe -m pytest -q` | `1448 passed, 14 failed, 4 warnings in 236.74s` | Fallos ajenos en embeddings/caché concurrentes; firma `embedding_cache_key` y 422 derivados |
| Blind20 baseline | `tools.evaluate_cases` sobre predicción y referencia congeladas | SHA-256 `aeee1b68e563f6a8ad985557f6368491effecf54600f6e602a94ee4b57b7b662`, idéntico al informe previo | PlankAssembly paramétrico, `development_diagnostic` |
| Blind20 final | `tools.evaluate_cases` sobre predicción y referencia congeladas | SHA-256 `1e420480e462d176639fb6c923a3f836716c8cd64ad8f21778bf98ba91072340`, idéntico al informe previo | Sin coste, horas ni sesiones |
| Economía pública | recálculo LOPO desde predicciones congeladas y fuente verificada | n=4; coste MAE 48,82 PLN; horas MAE 0,46775; recibo SHA-256 `77291734d25eb5f535edc4b335a0b408f53b80effce6ece56ae54c634783f8c8` | Presupuestos académicos, no ERP ni costes ejecutados |
| Revisión independiente | revisor `/root/reviewer` | APPROVE sin bloqueos | Etiquetas de evidencia dependen de attestación externa, no verificación criptográfica |

## Bloqueos y cierre

- Bloqueos: ninguno para tooling. La medición empresarial requiere datos y participantes aportados fuera del repositorio.
- Pendientes: recoger la primera cohorte real y conservar su custodia privada.
- Reservas liberadas: ninguna.
- Entrega: scorer, CLI, tests, protocolo y recibos locales comunicados a `/root` y al revisor.
