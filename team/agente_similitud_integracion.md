# Agente de integración pública de similitud

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA de integración pública; no representa a una persona.
- Rol: integración de backend, API, interfaz, evaluación y operación de Biblioteca/similitud.
- Archivo creado y designado explícitamente: `team/agente_similitud_integracion.md`, delegación de `/root` del 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto: portar exclusivamente las correcciones revisadas de similitud y Biblioteca a la base pública vigente, preservando CAD, reconstrucción y explorador.
- Referencia del plan: `docs/superpowers/plans/2026-11-14-similarity-repair.md`.
- Estado: implementando helpers compactos de contexto crítico y enlace de regiones visuales, por transferencia explícita de `/root`.

## Alcance y reservas

- Archivos reservados en el bloque vigente: `backend/app/general_furniture/context_payload.py`, `backend/tests/test_general_furniture_context_payload.py` y este registro.
- Dependencias que solo leeré: checkout fuente `Vexplorer` y sus cambios locales revisados.
- Archivos compartidos que requieren coordinación: contratos aditivos, rutas públicas y frontend; la delegación centralizada asigna su integración completa aquí.
- Solapes detectados y acuerdo para resolverlos: ningún otro agente escribe el target; se preservarán todas las capacidades CAD de la base `d0ea7a8`.

## Hecho en el último bloque

- Portados motor, contratos aditivos, API, política pública, interfaz, evaluación, backfill y release reproducible sin reemplazar capacidades CAD.
- Biblioteca pública permite lectura, agrupación, búsqueda y guardado offline elegible; embeddings de pago requieren autenticación.
- El mueble general queda explícitamente fuera del descriptor de Biblioteca hasta un contrato posterior.
- Diagnóstico read-only de DXF públicos 016/030 completado; ownership de helpers de contexto transferido y confirmado con el agente motor.
- Añadidos helpers puros para enlazar regiones candidatas con crops visuales y proyectar el contexto crítico sin duplicar propuesta y borrador.

## Siguiente bloque

- Implementar por TDD los helpers acordados; entregar firma al agente motor para integración en `live/autonomous`.
- Esperar integración del agente motor en `live/autonomous` y revisión focal conjunta.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | No copiar parches globales ni archivos frontend completos | El checkout fuente contiene trabajo local ajeno y la base pública tiene capacidades CAD posteriores | Delegación de `/root` |
| 2026-11-14 | Exponer solo lectura/búsqueda y guardado offline elegible de Biblioteca | Preservar restricciones económicas y evitar generación pública pagada | Refinamiento de política de `/root` |

## Dependencias / avisos

- Necesito de: resultado fuente revisado y política pública comunicada por coordinación.
- Afecta a: contratos de similitud, API de Biblioteca, caché estática y frontend.
- Aviso realizado: ownership y política confirmados a `/root` el 2026-11-14.
- Cambio de `contratos/`: aditivo acordado por el swarm de motor/API/UI y autorizado para integración por `/root`.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Backend/API/tooling focal | `python -m pytest -q backend/tests/test_similarity_technical.py backend/tests/test_library_publication.py backend/tests/test_backend_library_api.py backend/tests/test_static_cache_headers.py backend/tests/test_private_auth.py tests/test_similarity_regression.py tests/test_backfill_library.py tests/test_build_release.py tests/test_rehearse_library_release.py` | 63 passed | Sin red ni despliegue |
| Interfaz focal | `node --test frontend/tests/similarity-ui.test.js frontend/tests/ui-behavior.test.js frontend/tests/integration-navigation.test.js frontend/tests/ui-contract.test.js` | 43 passed; distingue proveedor configurado/índice vacío/caché sin proveedor, oculta Historial y Coste públicos | QA real delegado a coordinación |
| Sintaxis y lint | `node --check frontend/app.js`; `python -m ruff check ...` | correcto; All checks passed | Archivos Python tocados |
| Release v2 | `python -m tools.rehearse_library_release --repository . --output .runtime/release-similarity-v2 --expected-head d0ea7a85e787f4358ab4dbb05ea0250395f2083b` | dos archivos idénticos; SHA-256 `15cd6c2474df368ff4716f881b38062995c593c55f633097effd756b7651005e`; 147 ficheros | Sin acciones remotas; v1 descartado |
| Release v3 | `python -m tools.rehearse_library_release --repository . --output .runtime/release-similarity-v3 --expected-head d0ea7a85e787f4358ab4dbb05ea0250395f2083b` | dos archivos idénticos; SHA-256 `37fded2d73c4a00a12d88b76609184869fa760a8bc6b7d8ba17c8ad454d18296`; 147 ficheros; 8 rutas operativas requeridas presentes | Sin acciones remotas |
| Release v4 | `python -m tools.rehearse_library_release --repository . --output .runtime/release-similarity-v4 --expected-head d0ea7a85e787f4358ab4dbb05ea0250395f2083b` | dos archivos idénticos; SHA-256 `a86eb821494c529384daa294eaf27179d6947cbed4eee9b9f9d70e6fd0dd37b6`; 147 ficheros; incluye regresión caché sin proveedor | Final; v3 supersedido; sin acciones remotas |
| Contexto crítico general | `python -m pytest -q backend/tests/test_general_furniture_context_payload.py`; `python -m ruff check backend/app/general_furniture/context_payload.py backend/tests/test_general_furniture_context_payload.py` | 8 passed; Ruff limpio; DXF 016 enlaza 31/31 candidatos y 030 40/40 | Sin proveedor, GT, sidecars ni despliegue |

## Bloqueos y cierre

- Bloqueos: ninguno.
- Pendientes: suite integral y navegador independientes coordinados por `/root`.
- Reservas liberadas: target completo tras entrega.
- Entrega a otra persona: `/root`, con rutas, diff y evidencia focal.
