# PR2 — integración frontend de embeddings

## Identidad y autorización

- Identidad: agente de IA de revisión e integración; no representa a una persona.
- Autorización: delegación expresa del swarm GPT-6.1 Sol para PR2 y autorización del usuario para registros `agente_pr2_*`.
- Fecha: 2026-11-14.

## Alcance

- Revisión inicial del frontend de similitud y del aviso de precedentes.
- Correcciones acotadas a `frontend/app.js`, sus pruebas y este registro.
- Sin cambios de contratos Pydantic; coordinación mantiene la ampliación de la petición de similitud.

## Hallazgos y estado

- El aviso usaba un umbral fijo de cliente en vez de la calibración del servidor; coordinación implementará `threshold_kind=near_duplicate` y devolverá `threshold_used`.
- `resetRunUi()` conservaba visible el aviso del documento anterior y no invalidaba su petición.
- El aviso no reutilizaba la etiqueta humana ya cargada en `state.libraryItems`.
- El checkout original contiene una interfaz de similitud más nueva; una eventual reconciliación debe conservarla como base y portar selectivamente este PR.

## Verificación

- `npm ci` completado; dependencia `three` instalada desde el lockfile.
- Baseline `npm test`: 206 aprobadas, 0 fallos.
- RED focal: las dos nuevas regresiones fallaron por ausencia de invalidación/limpieza y etiqueta de biblioteca.

