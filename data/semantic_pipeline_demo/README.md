# Demo completa con embeddings ya calculados

Este paquete reúne el [pipeline de plank-030/plank-016 y mesas](../plank_pipeline_demo/README.md) y los resultados del explorador semántico en **un solo backup restaurable**. No necesita Gemma, DINOv3, MiniLM, GPU, PyTorch, Transformers, Codex ni una API de IA en ejecución. La aplicación sirve los vectores y renders persistidos, consulta vecinos por coseno y muestra las clasificaciones y proyecciones guardadas.

## Arranque inmediato

Desde la raíz del repositorio, con las dependencias habituales de la app instaladas (`pip install -e ".[test]"` y `npm ci --prefix frontend`):

```powershell
python -m tools.backup restore --archive data/semantic_pipeline_demo/demo-runtime.zip --destination .runtime/demo-completa-offline
$env:VEXPLORER_ENV = "local"
$env:VEXPLORER_AUTH_ENABLED = "false"
$env:VEXPLORER_ROOT_PATH = ""
$env:VEXPLORER_DATA_DIR = (Resolve-Path .runtime/demo-completa-offline).Path
$env:VEXPLORER_HISTORY_DB = Join-Path $env:VEXPLORER_DATA_DIR "history.sqlite3"
$env:VEXPLORER_COST_CATALOG = (Resolve-Path data/semantic_pipeline_demo/catalog.json).Path
$env:VEXPLORER_EXPLORER_ENABLED = "1"
$env:OPENAI_API_KEY = ""
$env:VEXPLORER_JEV_API_KEY = ""
$env:VEXPLORER_JEV_DAILY_ATTEMPTS = "0"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18864
```

Usar un destino nuevo. No pasar `--env-file .env`. No instalar los extras de modelos para presentar esta demo. La instalación inicial de dependencias sí requiere tener sus paquetes disponibles; durante la demo no se descargan modelos.

- **[Explorador de embeddings](http://127.0.0.1:18864/explorer.html)**: seleccionar catálogo, seleccionar plano, consultar mapa/vecinos, comparar representaciones y ver clasificación donde existe.
- **[plank-030](http://127.0.0.1:18864/?run=run-9eb5e3aca8a04331ac0b0d3e5e2f2f40)**: vistas, medidas, BOM, revisión y escena esquemática guardadas.
- **[plank-016](http://127.0.0.1:18864/?run=run-dbf758e4fbcd4b19bff8552201a48d4a)** y **[mesa acotada](http://127.0.0.1:18864/?run=run-161fc0b9bf7c46f499ddf84abe105d9b)**: otros recorridos del mismo runtime.

No hay que restaurar primero el paquete anterior: este ZIP ya contiene sus tres bases y documentos, además de `semantic_explorer.sqlite3`.

## Catálogos preparados

| Catálogo | Datos | Representaciones guardadas |
|---|---|---|
| `eg2-{text,image,mixed}-{256,768}` | 117 planos por espacio | Seis espacios de EmbeddingGemma 2; kNN cacheado en mixto 768 |
| `dinov3-image-384` | Los mismos 117 planos | DINOv3 imagen, 384 dimensiones |
| `minilm-text-384` | Los mismos 117 planos | MiniLM texto, 384 dimensiones |
| `cad-eg2-logreg373` | 373 dibujos CAD | EG2 mixto 768 y regresión logística cacheada |
| `engineering-eg2-mixed-768` | 14 dibujos mecánicos | EG2 mixto 768 |
| `plank-views-eg2-mixed-768` | 30 vistas: frontal/lateral/superior de plank-001 a plank-010 | EG2 mixto 768, recuperación entre vistas del mismo objeto |
| `pilot-eg2-demo` | 117 planos más dos entradas de ensayo | EG2 mixto 768 y clasificación cacheada |
| Biblioteca de la instancia | Cuatro registros, dos descriptores únicos | OpenAI `text-embedding-3-small`, 256 dimensiones, ya persistidos |

Son **12 catálogos, 1.472 filas vectoriales**, más cuatro registros de biblioteca: **13 espacios consultables**. Las representaciones repetidas no equivalen a 1.476 muebles distintos. Hay 609 clasificaciones cacheadas entre los catálogos EG2 mixto, CAD y piloto; sus scores no están calibrados y mantienen `needs_review`.

Los embeddings Plank preexistentes cubren plank-001 a plank-010. No se han inventado embeddings para plank-016/plank-030: estos dos modelos están disponibles en el recorrido de despiece, procedentes del paquete anterior. Tampoco se finge que un miembro del catálogo externo tenga una ejecución de despiece asociada: los catálogos aportan renders, vectores y metadatos; solo la biblioteca enlaza runs donde existe ese vínculo.

## Contenido portable

- `demo-runtime.zip`: backup nativo v2 de cuatro bases SQLite y documentos. Incluye biblioteca, histórico, costes, propuestas, revisiones, láminas y escenas del paquete Plank, más releases semánticos, vectores, imágenes, clasificación cacheada y mapas PCA persistidos.
- `portable-inputs.zip`: manifiestos, renders PNG, NPZ y metadatos originales verificados de los once corpus base; conserva también los dos dibujos añadidos al piloto y los clasificadores numéricos kNN/logística. Se puede extraer y republicar con `tools.publish_semantic_explorer`, sin ejecutar encoders. Los NPZ originales mantienen sus bytes; las copias portables de manifiestos registran la procedencia de sus hashes.
- `vectors/*.npz`: exportación de todos los vectores **activos** de los doce catálogos, con `ids` y `embeddings`, sin pickle. Son los valores persistidos, exportados como float64; no equivalen byte a byte al NPZ original de entrenamiento. Modelo, dimensión y revisión están en `manifest.json`.
- `snapshots/*.json`: respuestas completas de los trece mapas, miembros, coordenadas, categorías y clasificaciones. PCA solo sirve para visualizar; la recuperación usa las dimensiones originales.
- `neighbors/*.json`: diez vecinos precalculados por cada miembro de los doce catálogos, con coseno, excluyendo la propia consulta y resolviendo empates por ID. La app consulta los vectores locales para permitir filtros; no ejecuta un modelo para ello.
- `spaces.json`, `manifest.json`, `verification.json`: inventario, procedencia y comprobaciones. Los hashes del manifiesto cubren todos los archivos del paquete salvo el propio manifiesto.

## Alcance offline

Funcionan la selección por ejemplo, filtros de metadatos, mapas, vecinos, comparación de representaciones compatibles, previews y clasificación guardada. Se conservan los costes y los resultados de despiece existentes.

Un dibujo nuevo sin vector, una consulta semántica de texto libre que necesite codificación, una nueva propuesta de despiece o una opinión nueva de Jev no se resuelven con estos datos. El filtro de texto del explorador es léxico. Jev está desactivado. Las categorías editoriales y propuestas de clasificación no se convierten en confirmaciones ni presupuestos.

## Procedencia y verificación

Datos preexistentes de `D:/Vexplorer-semantic-lab/explorer-portable-20261114`, sus corpus `cross-dataset`, y el runtime verificado del explorador semántico. Los resultados de inferencia se conservan; esta entrega solo prepara, publica localmente y empaqueta sus datos. Las condiciones de las fuentes siguen descritas en [operación del explorador](../../docs/semantic-lab/OPERACION_EXPLORADOR.md), [laboratorio](../../docs/semantic-lab/INTEGRACION_EXPLORADOR.md) y [PlankAssembly](../../docs/PLANKASSEMBLY.md). Se publica este conjunto de demo por solicitud explícita del usuario; no se publican pesos ni credenciales.

Verificación con conexiones externas bloqueadas: 91 comprobaciones HTTP correctas, los trece mapas accesibles, tres búsquedas por espacio y previews de muestra. Todos los renders activos se verificaron por SHA-256. El backup se restauró en otra carpeta y los trece snapshots resultantes fueron idénticos. No se importaron `torch`, `transformers` ni `sentence_transformers`. Las doce ejecuciones del paquete Plank permanecen en el runtime combinado; se comprobó también el derivado de plank-030. El detalle está en `verification.json`.

Pruebas: `python -m pytest -q backend/tests/test_semantic_explorer.py backend/tests/test_explorer_models.py backend/tests/test_explorer_api.py tests/test_explorer_backup.py` → **34 passed**, una advertencia de deprecación Starlette/httpx. CRC de ambos ZIP y revisión de patrones de credenciales, incluidos sus contenidos descomprimidos, comprobados antes de publicar. `.gitattributes` conserva los bytes y hashes entre Windows y Linux.
