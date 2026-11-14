# Agente de integración PR1 — CAD determinista

## Identidad y autorización

- Identidad: agente de IA de integración CAD; no representa a una persona.
- Autorización: delegación explícita del coordinador tras congelar production en `056ec71`.
- Fecha: 2026-11-14.

## Tarea y alcance

- Portar selectivamente el tercer bloque de PR1 sin reintroducir contratos ni implementaciones legacy.
- Propiedad temporal exclusiva: `backend/app/ingesta/dxf_reader.py`, `backend/app/geometria/extraction.py`,
  `backend/app/servicios/decomposition.py`, `backend/app/validador/plausibilidad.py`, pruebas CAD/validador
  específicas, `pyproject.toml`, este registro y `.runtime/production/pr1-port-report.md`.
- Fuera de alcance: contratos, harness, prompts, tools, API/main, repository y frontend; pertenecen al agente
  de replay o al coordinador.

## Objetivos verificables

- Sustituir componentes de líneas O(n²) por union-find determinista y medir 25.000 líneas.
- Asociar curvas exactas a regiones por su geometría propia.
- Conservar filas de taladros y líneas ocultas como evidencia neutral, sin forzar roles.
- Clasificar paperspace de forma acotada: anotaciones informativas, cotas requieren revisión.
- Detectar cotas no apoyadas en geometría real mediante segmentos/curvas, sin falsos pases por vértices ajenos.
- Añadir `ruff` al extra de desarrollo sin alterar package-data vigente.

## Estado

- Port CAD implementado por TDD; no hay commit ni merge autorizado.

## Dependencias / avisos

- El agente de replay posee contratos/harness/main/repository; no se editarán desde este bloque.
- El coordinador integrará commits y ancestry del PR después de verificar todos los ports.

## Verificación

- Regresiones nuevas: `8 passed` tras observar primero 7 fallos esperados.
- Suite CAD/validador focal: `83 passed in 1.65s`.
- Benchmark union-find: tres pasadas de 25.000 líneas en 0,028256 / 0,024043 / 0,032230 s,
  25.000 componentes y el mismo SHA-256 de orden en las tres.
- Ruff global sobre los cinco módulos/prueba propios: `All checks passed!`.
- Suite Python compartida durante implementación concurrente de replay: `398 passed, 2 failed`; ambos fallos
  pertenecen exclusivamente a `test_pr1_replay_api.py` y se comunicaron al coordinador. Ningún fallo CAD.
