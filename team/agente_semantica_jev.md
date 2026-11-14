# Agente de comparación Jev — laboratorio semántico

## Identidad y autorización

- Identidad: agente de IA de comparación Jev; no representa a una persona.
- Autorización explícita: ejecutar la comparación real con `jev-1.14.0` usando la credencial local designada, sin copiarla ni persistirla.
- Trabajo aislado en el worktree `semantic-lab`; el coordinador realizará integración, commit y push.

## Alcance y reservas

- Propiedad exclusiva: `tools/semantic_lab/jev_comparison.py`, `tests/test_semantic_lab_jev_comparison.py`, `docs/semantic-lab/COMPARACION_JEV.md`, `docs/experiments/classifier-comparison-2026-11-14/jev-summary.json` y este registro.
- Artefactos crudos, respuestas, caché y prerregistro: fuera de Git bajo el laboratorio externo.
- Solo lectura: manifiestos, renders, credencial local designada y resto del repositorio.
- No modificar JEV, Reto Maisa, contratos, backend, frontend ni módulos semánticos ajenos.

## Protocolo fijado antes de métricas

- Evaluación post-hoc, no ciega: core validation+test (35), CAD-extra validation+test (111) y engineering OOD (14).
- Dos modos por muestra: texto geométrico y texto más el mismo render PNG 384×384 empleado por EG2.
- Una petición por muestra y modo, con Choice cerrado, Choice abierto con `OTHER`/`UNKNOWN` y Noul independiente de suficiencia.
- Modelo fijo `jev-1.14.0`; sin ejemplos, referencias, nombres de archivo ni etiquetas de la muestra en el estado.
- Errores API permanecen errores y cuentan en el denominador; no se convierten en `UNKNOWN`.

## Estado

- Implementación y ejecución terminadas; pendientes verificación focal final y entrega al coordinador.
- Prerregistro externo SHA-256: `9c061f2e714051f87bac2eeaf0ebd61089cc35b12f720cb6fef495eb4f14275a`.
- Smoke de imagen sobre core train: HTTP 200, `jev-1.14.0`, sin persistir entrada ni credencial.
- Batería: 320/320 respuestas válidas, cero errores API.
- Core mixto test: macro-F1 0,9143; CAD-extra mixto test: 0,5249; engineering OOD abierto: 13/14 abstenciones con imagen.

## Dependencias / avisos

- La API vigente admite texto e imágenes; la inspección anterior del repositorio JEV reflejaba solo su adaptador histórico de texto.
- Los holdouts ya fueron abiertos en experimentos anteriores; ninguna cifra nueva se presentará como blind test.

## Verificación

- TDD RED: import falló porque `tools.semantic_lab.jev_comparison` no existía.
- TDD GREEN inicial: `9 passed`; cierre tras hardening y paridad métrica: `16 passed`.
- Ruff focal: `All checks passed!`.
- Auditoría externa: 320 registros, 320 hashes de petición únicos, 320 entradas de caché; búsqueda de credenciales, rutas e inputs crudos sin hallazgos.
- Los 320 registros usaron un intento HTTP cada uno; no hubo reintentos. El hardening posterior no se atribuye retroactivamente al lote.
- Paridad métrica recalculada exclusivamente desde los 320 registros guardados, sin API; el resumen previo queda externo como `summary-before-metric-parity.json`.
- Auditoría post-hoc sin API: 160/160 pares texto+PNG coinciden con metadatos EG2 y 320/320 payload hashes coinciden con los registros Jev; digest `ac6335e8500a6796b97fb9b0a657687ee8eda47695c767a284097174d03dda89`.
