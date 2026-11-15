# Demo ampliada: pipeline, embeddings, Construcción 3D, piezas y PDF/DWG

Backup único que incorpora la [demo de embeddings y Plank](../semantic_pipeline_demo/README.md) y los datos preparados que faltaban: **10 trabajos de Construcción 3D**, **5 ejecuciones de piezas separadas** y **9 documentos PDF/DWG**, contando originales y páginas seleccionadas. Total: **20 ejecuciones, 8 registros de biblioteca y 14 espacios vectoriales**. Abrir resultados existentes no ejecuta modelos ni necesita API, Codex o conversor DWG.

## Restaurar y arrancar

Desde la raíz del repositorio, con las dependencias habituales instaladas (`pip install -e ".[test]"` y `npm ci --prefix frontend`):

```powershell
python -m tools.backup restore --archive data/full_app_demo/demo-runtime.zip --destination .runtime/demo-app-completa
$env:VEXPLORER_ENV = "local"
$env:VEXPLORER_AUTH_ENABLED = "false"
$env:VEXPLORER_ROOT_PATH = ""
$env:VEXPLORER_DATA_DIR = (Resolve-Path .runtime/demo-app-completa).Path
$env:VEXPLORER_HISTORY_DB = Join-Path $env:VEXPLORER_DATA_DIR "history.sqlite3"
$env:VEXPLORER_COST_CATALOG = (Resolve-Path data/full_app_demo/catalog.json).Path
$env:VEXPLORER_EXPLORER_ENABLED = "1"
$env:OPENAI_API_KEY = ""
$env:VEXPLORER_JEV_API_KEY = ""
$env:VEXPLORER_JEV_DAILY_ATTEMPTS = "0"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18864
```

El destino debe ser nuevo; este ZIP ya incluye los paquetes anteriores, no se restauran unos sobre otros. No usar `--env-file .env` ni reemplazar el runtime productivo. Si ya está ejecutándose la demo anterior en ese puerto, detener ese proceso antes de arrancar esta instancia.

## Enlaces de la demo

| Recorrido | Abrir después de restaurar |
|---|---|
| Embeddings, mapas y vecinos | [Explorador](http://127.0.0.1:18864/explorer.html) |
| plank-030 | [Resultado guardado](http://127.0.0.1:18864/?run=run-9eb5e3aca8a04331ac0b0d3e5e2f2f40) |
| plank-016 | [Resultado guardado](http://127.0.0.1:18864/?run=run-dbf758e4fbcd4b19bff8552201a48d4a) |
| Mesa acotada y coste | [Resultado guardado](http://127.0.0.1:18864/?run=run-161fc0b9bf7c46f499ddf84abe105d9b) |
| Piezas separadas revisadas | [Revisión 2](http://127.0.0.1:18864/?run=run-6ddf07a4229b40949f5b8d1b1b128e31) |
| Otra ejecución de piezas separadas | [Revisión 2](http://127.0.0.1:18864/?run=run-c321bf839d8c4dda9e279b172c10992d) |
| PDF raster analizado | [Propuesta guardada](http://127.0.0.1:18864/?run=run-7267675e450042d7af5ad956fdc0593b) |
| **Construcción 3D, versión inicial** | [Mesa, revisión 1](http://127.0.0.1:18864/reconstruction.html?job=3894284a17bb46dbbcc0766766f4195a&run=run-b1537484028f47f3838301234173216f) |
| **Construcción 3D, refinamiento guardado** | [Mesa, revisión 2](http://127.0.0.1:18864/reconstruction.html?job=a174a6e50eab4111858b22f3b800d0f9&run=run-b1537484028f47f3838301234173216f) |
| Construcción 3D, caso del estudio | [Caso 01](http://127.0.0.1:18864/reconstruction.html?job=00dbf06fac402177f21a35d2a2e31ecc) |
| Control 3D sin evidencia suficiente | [Abstención](http://127.0.0.1:18864/reconstruction.html?job=07f54e99bbf44b4ea75f4577f6fc5aba) |
| Control 3D con aclaraciones guardadas | [Revisión hija](http://127.0.0.1:18864/reconstruction.html?job=69f635e5a57b48c4b7856fa437bf6644) |

**Para mostrar Construcción 3D, usar los enlaces con `job=`.** El botón de la aplicación que abre únicamente `?run=` inicia el flujo de generación, no selecciona automáticamente un trabajo anterior. No pulsar Generar ni enviar un nuevo refinamiento sin proveedor. Sí se pueden inspeccionar el resultado, las piezas, las descargas y la versión anterior ya guardada. Se conservan los seis casos del estudio y las dos cadenas padre/hijo; todos los enlaces están en `manifest.json`.

Los IDs `study:case-*` y `smoke-unscaled-table` identifican trabajos autónomos del estudio, no runs de despiece. No se inventaron runs para ellos. La mesa de reconstrucción tiene un run real de ingesta, pero no una propuesta en `/general`; su resultado está en el trabajo de reconstrucción.

## Documentos convertidos, sin volver a convertir

Los originales, previews y derivados están en el runtime y también exportados en `documents/`. Ejemplos servidos por la app:

- DWG: [original](http://127.0.0.1:18864/api/v1/documents/doc-a9c588ba612346238135f9d283aefcfb/original), [DXF ya normalizado](http://127.0.0.1:18864/api/v1/documents/doc-a9c588ba612346238135f9d283aefcfb/normalized.dxf).
- PDF vectorial: [original](http://127.0.0.1:18864/api/v1/documents/doc-9d5160b61b14433d866a69ea2cc81a29/original), [página normalizada](http://127.0.0.1:18864/api/v1/documents/doc-9d5160b61b14433d866a69ea2cc81a29/normalized.dxf).
- PDF raster: [original](http://127.0.0.1:18864/api/v1/documents/doc-a495f8e6c9b24e17840e4ef2aa9f789e/original), [preview guardada](http://127.0.0.1:18864/api/v1/documents/doc-586b1d861e3345678b2f3ed36698262c/pages/1/preview.png).

Los nueve documentos no representan nueve diseños únicos. Los PDFs raster siguen sin geometría métrica; la página vectorial conserva su decisión de escala y el aviso `DO NOT SCALE` del ensayo. Tener una conversión DWG guardada no equivale a tener una inferencia de despiece para ese DWG. Reimportar/analizar archivos nuevos es otra operación y puede requerir conversor o proveedor.

## Archivos y procedencia

- `demo-runtime.zip`: backup nativo v2 con documentos, reconstrucciones y ocho bases: las cuatro de pipeline/histórico/explorador y las cuatro auxiliares de precedentes. Estas últimas están vacías; no contienen decisiones o herrajes inventados.
- `reconstruction/<job_id>/`: todos los archivos existentes de los diez trabajos: estado, imagen fuente, GLB cuando existe, escenas, piezas, BOM, renders, máscaras, comprobaciones y metadatos de revisión/contexto cuando el trabajo los guardó. Se conserva la abstención sin añadirle una construcción ficticia.
- `runs/<run_id>/`: exportaciones de las cinco ejecuciones de piezas separadas y propuestas generales disponibles. El backup contiene también todas las revisiones y trazas originales de los 20 runs; los exports del paquete anterior siguen accesibles en sus carpetas versionadas.
- `documents/<document_id>/`: originales PDF/DWG, manifiestos y todos sus enlaces de artefactos comprobados.
- `manifest.json`: orígenes importados, conteos por tabla, runs, documentos, espacios, enlaces de trabajos y hashes.
- `verification.json`: consultas ejecutadas después de restaurar y único recurso opcional ausente.

Se tomó como base el backup semántico publicado y se añadieron datos de `.runtime/parts-live-final-20261114`, `.runtime/integral-audit-local/data-dwg`, `.runtime/pdf-raster-acceptance/data-8793` y `D:/Vexplorer-idol-study/{viewer-data,refinement-v1}`. La unión conserva IDs y revisiones, rechaza colisiones con contenidos distintos y no modifica las fuentes locales. No se importó el histórico económico de ensayos auxiliares: se conserva el conjunto publicado de 19 registros.

Las reconstrucciones proceden de propuestas/ensayos descritos en [resultados 3D](../../docs/RECONSTRUCCION_3D_RESULTADOS.md) e [incremento y refinamientos](../../docs/RECONSTRUCCION_3D_INCREMENTO.md). Mantienen `needs_review`, supuestos y ausencia de certificación de fabricación. Las condiciones y atribución de fuentes se mantienen; la publicación de estos datos de demo responde a la instrucción explícita del usuario.

## Verificación y límites

Se comprobaron **486 consultas y descargas** con conexiones externas bloqueadas, incluyendo todos los artefactos anunciados de los diez trabajos, fuentes PDF/DWG, cinco recorridos de piezas y snapshots/búsqueda de los **14 espacios**. El mismo recorrido se repitió sobre el backup restaurado. Se conserva un 404 esperado de propuesta general en el run de ingesta usado por Construcción 3D; no afecta a sus trabajos guardados.

Pruebas: `python -m pytest -q tests/test_backup.py tests/test_explorer_backup.py tests/test_reconstruction3d_router.py backend/tests/test_parts_reconstruction.py` → **50 passed**, una advertencia de deprecación Starlette/httpx. La verificación cubre datos/API y restauración, no una nueva evaluación visual exhaustiva.

No se añadieron nuevos embeddings de plank-016/plank-030, dictámenes Jev ni resultados de precedentes: no existían preparados. La generación de propuestas nuevas, refinamientos nuevos o embeddings de nuevas entradas sigue requiriendo sus modelos. Este paquete permite presentar los resultados guardados de las funcionalidades cubiertas sin ejecutarlos de nuevo.
