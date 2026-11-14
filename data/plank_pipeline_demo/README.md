# Pipeline guardado para demo sin API ni Codex

Instantánea del 14 de noviembre de 2026. Abrir resultados existentes reproduce el recorrido de la aplicación sin ejecutar inferencia. Incluye **plank-030**, **plank-016**, mesas de ejemplo y un control sin unidades: 12 ejecuciones conservadas, incluidas revisiones anteriores y un primer intento incompleto de plank-030.

## Arranque

Desde la raíz del repositorio, con las dependencias de Python y `npm ci --prefix frontend` ya instaladas:

```powershell
python -m tools.backup restore --archive data/plank_pipeline_demo/demo-runtime.zip --destination .runtime/demo-plank-offline
$env:VEXPLORER_ENV = "local"
$env:VEXPLORER_AUTH_ENABLED = "false"
$env:VEXPLORER_ROOT_PATH = ""
$env:VEXPLORER_DATA_DIR = (Resolve-Path .runtime/demo-plank-offline).Path
$env:VEXPLORER_HISTORY_DB = Join-Path $env:VEXPLORER_DATA_DIR "history.sqlite3"
$env:VEXPLORER_COST_CATALOG = (Resolve-Path data/plank_pipeline_demo/catalog.json).Path
$env:OPENAI_API_KEY = ""
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18864
```

El destino de restauración debe ser nuevo. No usar `--env-file .env`. La app necesita su backend local, pero ninguna API de IA ni sesión de Codex. No sustituir los datos del servicio productivo por esta instantánea.

| Caso | Enlace después de restaurar | Contenido |
|---|---|---|
| **plank-030, ejecución recomendada** | [Abrir](http://127.0.0.1:18864/?run=run-9eb5e3aca8a04331ac0b0d3e5e2f2f40) | Propuesta 1/revisión 1, 10 tipos, 16 ocurrencias provisionales, medidas y evidencia, esquema SVG/DXF, BOM y escena 3D |
| plank-016 | [Abrir](http://127.0.0.1:18864/?run=run-dbf758e4fbcd4b19bff8552201a48d4a) | Otro caso del dataset, propuesta/revisión y derivados guardados |
| Mesa con revisión y coste | [Abrir](http://127.0.0.1:18864/?run=run-161fc0b9bf7c46f499ddf84abe105d9b) | General acotado, láminas por pieza, despiece, 3D y coste sintético guardado |
| Mesa de dimensiones distintas | [Abrir](http://127.0.0.1:18864/?run=run-d5b7fce18fee4c699bc49a5110c75240) | Plano, extracción y estado de revisión conservado |
| Control sin unidades | [Abrir](http://127.0.0.1:18864/?run=run-54cfb9b2022341b790b1615ad3a3387c) | Conserva faltantes y límites del resultado |

Todos los IDs, fuentes y rutas están en [manifest.json](manifest.json). Las [otras cuatro demos sintéticas procesadas](../../docs/DEMO_DATOS_PROCESADOS.md) siguen disponibles en su paquete independiente.

## Guion

1. Abrir el enlace de plank-030; no volver a subir el archivo ni pulsar Agente en vivo/Nueva ejecución/Auto-revisión.
2. En Fuente, mostrar todas las vistas y CAD original. Seleccionar filas para inspeccionar medidas, cotas y referencias.
3. Mostrar revisión, esquema general, escena 3D y descargar BOM CSV/JSON y esquema SVG/DXF.
4. Abrir plank-016 para mostrar otro modelo. Usar la mesa para las láminas por pieza y despiece de ese recorrido.
5. Consultar biblioteca geométrica y costes guardados. Hay 19 registros de histórico publicado, cuatro entradas de biblioteca, vectores cacheados y dos estimaciones de mesa. La recuperación que requiera generar un embedding nuevo sí necesita proveedor; los vectores guardados no habilitan cualquier consulta semántica offline.

Es una **demostración de resultados previamente calculados**, no inferencia nueva. Los registros originales mantienen `live`, `geometry_only` o replay según su procedencia histórica; abrirlos ahora no ejecuta esos modos. No se simulan confirmaciones humanas ni se eliminan advertencias. El caso económico con `run-564b920c178b4603bd98c86c65032557` es expresamente simulado.

## Archivos

- `demo-runtime.zip`: backup nativo v2 con las tres bases SQLite y los nueve documentos con sus manifiestos. Conserva resultados, ledger, propuestas, revisiones, intentos de montaje, eventos, jobs, grabación disponible, biblioteca, embeddings, histórico, costes y láminas almacenadas. El restaurador comprueba hashes e integridad SQLite.
- `runs/<run_id>/`: DXF de entrada, preview SVG, documento, ejecución, todas las revisiones de resultado, drawing/ledger y exports JSON/CSV. `events.json` conserva la traza.
- `general.json`, `derived.json`, `scene.json` y `artifacts/`: propuesta/revisión y todos los derivados disponibles del recorrido general. Para mueble general, **la escena correcta está en `derived.json`/`scene.json`**, no en la escena del export legado. BOM CSV/JSON y esquemas están en `artifacts/`.
- `table-artifacts/rN/`: las 16 láminas SVG/DXF persistidas de las mesas, con su revisión. Las respuestas de mesa, escena, explicaciones y coste se incluyen cuando existen.
- `stored/`: exportaciones JSON de propuestas/revisiones e intentos de montaje, histórico, embeddings, biblioteca, costes y grabación. Las columnas terminadas en `_json` y `payload` conservan el JSON serializado original.
- `catalog.json`: catálogo sintético usado para la demo de mesa.
- `manifest.json`: inventario con tamaño y SHA-256, identificación de casos y comprobaciones HTTP. El ZIP es la fuente de restauración; los JSON facilitan inspección e integración de una demo estática.

## Procedencia y límites

Fuente de esta instantánea: `.runtime/localhost-production/data`, exportada mediante backup SQLite y restaurada en un directorio separado. No contiene `.env`, claves de API, certificados TLS, claves privadas ni referencias privadas del evaluador. Los planos de PlankAssembly son vistas adaptadas del dataset [manycore-research/PlankAssembly](https://huggingface.co/datasets/manycore-research/PlankAssembly), revisión local `d1d4308f0ee0aac2f9f407b3533ff83ecee22d34`; la ficha archivada declara CC BY-NC-ND 4.0. Esta publicación de datos para demo responde a la solicitud explícita del usuario; no cambia las condiciones de la fuente. Véase [procedencia del corpus](../../docs/PLANKASSEMBLY.md).

`reviewed_incomplete` y `schematic_incomplete` se conservan. El 3D general distribuye tipos para inspección y no certifica montaje, uniones, mecanizados ni colisiones. No hay láminas por pieza/despiece del recorrido general donde el pipeline no las produjo. Las dimensiones propuestas conservan sus hipótesis y referencias. Los comparables económicos disponibles no acreditan un presupuesto del armario.

## Verificación de esta entrega

Se restauró el backup con el código de main base `026317f` y se abrió la aplicación mediante TestClient, con variables de proveedor eliminadas, clave vacía y conexiones externas bloqueadas durante la exportación. Se comprobaron 151 respuestas HTTP 200: ejecuciones, revisiones, planos, ledger, previews, exports, propuestas, derivados, escenas disponibles y biblioteca. Doce respuestas 404 corresponden a recursos opcionales que nunca se guardaron; se registran en el manifiesto, no se sustituyen por resultados inventados. Se exportaron además las 16 láminas almacenadas desde SQLite.

Esta verificación comprueba restauración y datos/API local. No es una nueva ejecución de inferencia ni una certificación visual exhaustiva del navegador. La guía histórica del ensayo original está en [demo-local-2026-11-14.md](../../docs/demo-local-2026-11-14.md).

Pruebas adicionales: `python -m pytest -q tests/test_backup.py tests/test_processed_demo.py` → **34 passed**, una advertencia de deprecación Starlette/httpx. Verificados todos los SHA-256 del manifiesto, integridad del backup, BOM/escenas no vacías de ambos Plank y ausencia de patrones de credenciales en archivos y contenido descomprimido del ZIP.
