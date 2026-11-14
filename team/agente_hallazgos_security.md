# Hallazgos y correcciones de seguridad

## Identidad y autorización

- Nombre: `agente_hallazgos_security`
- Rol: aislamiento de propietarios y robustez ASGI.
- Autorización: el usuario autorizó explícitamente el swarm, sus registros y la implementación completa el 2026-11-14.

## Alcance

- `backend/app/main.py`: middleware JSON, autorización uniforme de documentos/runs y validación de IDs recibidos en body.
- `backend/app/servicios/repository.py`: migración y helpers de propietario de runs.
- Pruebas de seguridad enfocadas.
- No se editan las secciones de ciclo de vida/cancelación de jobs, propiedad de `agente_jobs`.

## Estado

- Terminado. `http.disconnect` ya corta la lectura y, tras reproducir un body completo, las recepciones siguientes se delegan al canal ASGI original.
- Los documentos, runs, rutas derivadas, IDs recibidos en JSON y jobs de reconstrucción validan propietario de forma uniforme.
- `runs.owner_actor` se persiste y migra solo con evidencia histórica unánime; los conflictos quedan cerrados para usuarios autenticados.

## Decisiones

- Los recursos ajenos se presentan como inexistentes (`404`) para evitar enumeración.
- El backfill de propietario solo acepta un actor histórico unánime; la ambigüedad falla cerrada con autenticación.
- La biblioteca es un catálogo compartido por publicación explícita; publicar no concede acceso al documento, run, resultados ni artefactos fuente.
- El modo público/local sin autenticación conserva compatibilidad mediante el actor técnico `local-demo`.

## Coordinación

- `agente_jobs` conserva las rutas y helpers de cancelación/listado y añade el invariante actor-job-run usando los helpers de este bloque.
- `main.py` y `repository.py` son compartidos; los cambios se limitan a las secciones acordadas.

## Pruebas

- TDD rojo observado: 7/7 pruebas iniciales fallaron por middleware, API/migración ausente y lecturas cruzadas.
- Verde focal final: `python -m pytest -q backend/tests/test_security_ownership.py backend/tests/test_private_auth.py backend/tests/test_private_jobs.py backend/tests/test_job_lifecycle.py backend/tests/test_private_repository.py backend/tests/test_job_recovery.py backend/tests/test_integral_api_integration.py` → 88 passed.
- `python -m ruff check backend/app/main.py backend/app/servicios/repository.py backend/tests/test_security_ownership.py` → limpio.
- `python -m py_compile ...` y `git diff --check` → correctos; los únicos avisos de finales de línea pertenecen a archivos semánticos ajenos.
- Suite backend completa observada durante la integración concurrente: 993 passed, 14 failed. Los 14 fallos pertenecen a la migración EmbeddingGemma/pruebas que aún envían `embedding_mode=openai` y a una firma de `embedding_cache_key`; no afectan este bloque y los resuelve el propietario semántico.
- Revisión independiente Astra: aprobada, sin hallazgos P1/P2 restantes en el alcance de seguridad.
- Robustez final: un manifiesto con audit o source de tipo no objeto se trata como corrupto, devuelve 404 en acceso directo y se omite de proyectos/ejecuciones. La regresión falló primero con 500/200 y quedó verde.
- Verificación fresca posterior al P2: test_security_ownership.py, test_private_auth.py y test_job_lifecycle.py dieron 43 passed; Ruff, py_compile y diff-check limpios.

## Cierre

- No quedan incidencias conocidas en este alcance.
- No se realizó commit; la integración final corresponde al coordinador.
