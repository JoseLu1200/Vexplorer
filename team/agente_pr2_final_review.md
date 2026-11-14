# Integración PR2 · correcciones finales de ingesta y visor

## Identidad y autorización

Agente de IA revisor/implementador. El coordinador del swarm autorizado por el usuario me asignó el 2026-11-14 dos correcciones concretas sobre el worktree `pr2-integration`, sin commits ni push.

## Alcance

- `frontend/core/drawing.js`
- `frontend/tests/drawing_conflict.test.js`
- `backend/app/geometria/extraction.py`
- pruebas de regresión relacionadas con DXF/POLYLINE
- este registro propio

El coordinador conserva `frontend/app.js`, contratos, integración y commits. No se modifica `backend/app/contratos/`.

## Estado

Implementación terminada, pendiente de integración por coordinación. Tras integrar upstream `1c22e1c`, ambos fallos se reprodujeron en RED y quedaron corregidos sin cambios de contrato.

## Decisiones

- El conflicto visual se derivará de warnings tipados por `source_entity_id` y de los puntos geométricos ya publicados.
- `POLYLINE` 2D planar cerrado compartirá el mismo recorrido determinista que `LWPOLYLINE`; no se admitirá geometría 3D ni bulges.
- Se conservarán los cambios nuevos de asignación multi-vista en `drawing.js`.

## Verificación

- RED frontend: `node --test frontend/tests/drawing_conflict.test.js` → 3 fallos esperados; los warnings reales no activaban conflicto.
- RED Python: `python -m pytest -q backend/tests/test_dxf_ingest_hardening.py -k 'feed_mounted'` → 1 fallo esperado; vista `UNKNOWN` en vez de `FRONT/TOP/SIDE`.
- GREEN frontend: `node --test frontend/tests/drawing_conflict.test.js frontend/tests/drawing_views.test.js` → 8 passed.
- GREEN Python: `python -m pytest -q backend/tests/test_dxf_ingest_hardening.py backend/tests/test_mounted_view_inference.py backend/tests/test_geometry.py` → 27 passed.

## Dependencias / avisos

El coordinador fusionó `1c22e1c` antes de autorizar escrituras. No hay otro escritor en los archivos anteriores durante este bloque.
