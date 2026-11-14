# Explorador semántico integrado — plan de implementación

> Ejecución nativa con `superpowers:executing-plans` y TDD; revisión independiente final.

**Objetivo:** búsqueda vectorial, mapa navegable y modelos locales/versionados enlazados a Vexplorer.
**Arquitectura:** API aditiva, NumPy para recuperación/proyección, SQLite para releases/retiradas/presupuesto; adaptadores del laboratorio para generación offline; frontend ES modules.
**Spec:** [INTEGRACION_EXPLORADOR](../../semantic-lab/INTEGRACION_EXPLORADOR.md).

## Restricciones

No tocar contratos compartidos ni trabajo UX ajeno. Sin mezcla de espacios, sin precios generados por modelos, sin pickle en HTTP. Nuevas rutas cubiertas por autenticación global; catálogo compartido de instancia, no multitenant. Semántica 768d preservada; PCA solo visual. Hasta 2.000 puntos, 4.096 dimensiones, 2 MiB/PNG. Revisión local conserva hipótesis y no impone aprobación humana al flujo autónomo existente.

## Focos de revisión

- Corrupción y duplicación de vectores: rechazo antes de activar.
- Cambios de revisión durante búsqueda: snapshot obsoleto, nunca respuesta mezclada.
- Retirada seguida de rollback: no resucitar ni servir render retirado.
- Clasificador/encoder incompatible: rechazo por identidad completa.
- Petición externa repetida: caché/presupuesto durable, sin gastar al navegar.

## Tarea 1: núcleo, modelos y releases

Archivos: `backend/app/semantic_explorer/{models,core,store}.py`, `backend/tests/test_semantic_explorer.py`.
Interfaces: `make_snapshot`, `search`, `ExplorerStore.publish/activate/retire/load`.
- [x] Escribir tests de coseno conocido, PCA degenerada, límites, rollback y hash.
- [x] Ejecutar pytest focal y observar RED.
- [x] Implementar contratos Pydantic, búsqueda/proyección y almacenamiento transaccional.
- [x] Ejecutar focal hasta GREEN.

## Tarea 2: modelos y preparación

Archivos: `classification.py`, `tools/publish_semantic_explorer.py`, `tools/prepare_semantic_explorer.py`, tests focales.
Interfaces: clasificador numérico kNN/logística; publicación desde manifiesto/NPZ de `encode_manifest`; preparación DXF por `extract_dxf` y adaptadores existentes.
- [x] Tests independientes de logits, kNN, incompatibilidad, hash e inputs exactos.
- [x] RED; implementar exportación segura de modelos propios y generación explícita/cacheada.
- [x] GREEN y prueba con artefactos reales disponibles sin abrir nuevas referencias privadas.

## Tarea 3: API y revisión opcional

Archivos: `service.py`, `router.py`, `review.py`, montaje mínimo en `main.py`; tests HTTP.
Interfaces: espacios, snapshot, vecinos, imagen, revisión Jev explícita; biblioteca desde repositorio actual.
- [x] RED con flag, revisión obsoleta, autenticación, imágenes/retiradas y presupuesto Jev.
- [x] Implementar adaptadores, endpoint y errores seguros; proveedor simulado solo en frontera HTTP.
- [x] GREEN y paridad de clasificación/búsqueda con corpus local.

## Tarea 4: visualizador y comparación

Archivos: `frontend/explorer.{html,js,css}`, `frontend/core/explorer.js`, enlace mínimo en `index.html`, tests JS.
- [x] RED de filtros, navegación, IDs y selección sin HTML interpolado.
- [x] Mapa SVG, zoom, lista accesible, vecinos, comparación, previews y revisión opcional.
- [x] GREEN, navegador escritorio/móvil, consola y rutas con prefijo.

## Tarea 5: operación, documentación y aceptación

Archivos: `tools/backup.py`, tests backup, `pyproject.toml`, documentos de arquitectura/operación/README y registro propio.
- [x] Test RED de copia/restauración del nuevo SQLite; implementar y GREEN.
- [x] Actualizar decisión/diseño con investigación y matriz implementado/pendiente.
- [x] Suite final: 721 Python / 151 JavaScript; lint focal, compileall y 252 enlaces locales aprobados.
- [x] Revisión independiente y corrección de hallazgos con pruebas.
- [x] Commit local de entrega; rama y worktree conservados, sin merge/push/despliegue remoto.

## Evidencia inicial

Base `83df72d`: 683 pruebas Python aprobadas en 85,41 s y 147 JavaScript. Investigación: 112 Markdown completos revisados e inventariados; 38 ramas locales y 8 refs remotas contrastadas. `main` remoto verificado en `dbd1bb6` al comenzar.
