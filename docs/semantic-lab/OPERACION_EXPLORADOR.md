# Operación del explorador semántico

**Demo sin encoders ni API:** el [paquete completo ya procesado](../../data/semantic_pipeline_demo/README.md) incluye doce catálogos activos, mapas, vecinos, renders y clasificaciones cacheadas, junto al pipeline de plank-030/plank-016. Restaurar ese backup permite usar esta pantalla sin volver a generar embeddings.

Implementación desde `83df72d`, integrada en `main` mediante `6ea3b64`. No implica despliegue remoto. [Diseño](INTEGRACION_EXPLORADOR.md), [decisión](DECISION_ARQUITECTURA_PRODUCCION.md) y [arquitectura](DISENO_ARQUITECTURA_PRODUCCION.md).

## Arrancar y explorar

Desde la raíz del worktree, con dependencias del proyecto instaladas:

```powershell
$env:VEXPLORER_EXPLORER_ENABLED="1"
$env:VEXPLORER_DATA_DIR=".runtime/semantic-explorer"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8787
```

Abrir `http://127.0.0.1:8787/explorer.html`, también enlazado desde Biblioteca. Sin corpus publicado ni revisiones con embeddings, el estado vacío es correcto. No se incluyen datos demo encubiertos. En producción usar el perfil privado de [PRODUCCION](../PRODUCCION.md); todas las rutas del explorador quedan bajo su autenticación.

Seleccionar espacio, seleccionar plano y leer sus vecinos por coseno. El filtro textual solo busca nombres/categorías. La comparación entre modelos exige el mismo hash de contenido; conserva rankings independientes. Categoría editorial, hipótesis de clasificador y campo confirmado se muestran diferenciados. Abrir la ejecución permite continuar con presupuesto/histórico donde existe ese vínculo.

## Publicar embeddings calculados

El directorio del operador contiene manifiesto del laboratorio, NPZ y JSON de metadatos contiguo (`embeddings.npz.json`). Los hashes de manifiesto, NPZ y entradas deben coincidir. Solo se copian PNG admitidos, vectores y metadatos permitidos; no originales CAD ni rutas absolutas. El publicador exige rutas relativas resueltas dentro del directorio del manifiesto; también rechaza enlaces simbólicos que salgan de él.

Los manifiestos antiguos del laboratorio contienen rutas absolutas. Preparar una copia portable primero: solo admite renders contenidos en el directorio original, conserva los bytes de embeddings y originales, registra el hash del manifiesto fuente y actualiza los hashes de la copia. No vuelve a ejecutar el encoder.

```powershell
python -m tools.stage_semantic_explorer --manifest D:/laboratorio/data/core/manifest.json --embeddings D:/laboratorio/embeddings/embeddinggemma2-mixed-768.npz --output D:/laboratorio/portable/core-eg2
```

```powershell
python -m tools.publish_semantic_explorer --db .runtime/semantic-explorer/semantic_explorer.sqlite3 publish --catalog core-eg2 --manifest D:/laboratorio/portable/core-eg2/manifest.json --embeddings D:/laboratorio/portable/core-eg2/embeddings.npz --activate
```

Los directorios anteriores son ejemplos que deben apuntar a artefactos propios/autorizados existentes. Repetir para EG2 imagen/texto/256, DINOv3 y MiniLM con nombres de catálogo distintos. Ningún comando descarga pesos ni ejecuta los scripts del dataset.

Para añadir clasificación, reproducir una receta ya seleccionada sobre la partición `train` del corpus autorizado. `knn` utiliza cinco vecinos/coseno/pesos por distancia; `logreg` utiliza embeddings L2 más features ordenadas, StandardScaler y C=0,1. No selecciona hiperparámetros ni evalúa test.

```powershell
python -m tools.train_semantic_classifier --manifest D:/laboratorio/portable/core-eg2/manifest.json --embeddings D:/laboratorio/portable/core-eg2/embeddings.npz --kind knn --output D:/laboratorio/portable/core-eg2/classifier.json
```

Añadir al comando `publish` los argumentos `--classifier RUTA.json --trusted-classifier-sha256 HASH`, usando el hash que imprime el entrenador. El JSON v2 liga parámetros numéricos, encoder completo, esquema de features y hashes de entrenamiento; un corpus incompatible se rechaza. Los Joblib antiguos no guardaban ese contrato y **no se aceptan ni se deserializan**. La clasificación se calcula durante publicación y queda cacheada, sin sklearn en el servidor web. No aporta calibración ni evidencia industrial nueva.

## Preparar planos nuevos

```powershell
python -m tools.prepare_semantic_explorer plano-a.dxf plano-b.dxf --output D:/laboratorio/nuevos/lote-001 --encode --python D:/laboratorio/venv/Scripts/python.exe --cache-dir D:/laboratorio/hf-cache --model embeddinggemma2 --mode mixed --dimensions 768
```

El entorno de inferencia debe tener los extras `semantic-models`/`semantic-lab` y pesos locales. La preparación reutiliza exactamente `extract_dxf` del laboratorio: render geométrico 384, seis observaciones y 27 features; textos del dibujo/nombres/etiquetas no entran al encoder. DXF no soportado falla explícitamente. Para DWG/PDF usar primero la normalización existente; un PDF raster no se convierte aquí en geometría inventada. El directorio de salida debe ser nuevo. Para planos demo/generados añadir `--synthetic`.

Publicar `manifest.json` y `embeddings.npz` de ese directorio. Para recuperar vecinos de un catálogo anterior del **mismo espacio**, usar `publish --catalog core-eg2 ... --extend-active --activate`; conserva el release anterior y añade los nuevos miembros. Si otro proceso cambia la activación durante la preparación, se rechaza el cambio de puntero y se conserva el release publicado para inspección. Un cambio de modelo/revisión/precisión/preprocesado exige otro catálogo/reindexación; se rechaza la mezcla. Para un control DINOv3 usar `--model dinov3 --mode image`; para MiniLM, `--model minilm --mode text`. No activar todos por defecto.

## Jev opcional

```powershell
$env:VEXPLORER_JEV_DAILY_ATTEMPTS="5"
# VEXPLORER_JEV_API_KEY se suministra mediante el entorno/gestor de secretos del servidor.
```

Sin clave y presupuesto positivo, el botón permanece desactivado. Un clic envía imagen y observaciones, cuenta un intento antes de salir a red y conserva el resultado permitido en SQLite. No hay reintentos automáticos. Respuestas idénticas reutilizan caché; errores son `provider_error`, no `UNKNOWN`. La clasificación abierta puede abstenerse. Ni score ni etiqueta aprueban piezas/precios. Un proceso caído con solicitud `pending` mantiene la reserva y no duplica automáticamente el gasto; requiere revisión operativa.

No se reutiliza automáticamente una credencial hallada en otros proyectos. La verificación de este incremento usa un doble HTTP en las pruebas Jev; cualquier nueva ejecución pagada debe registrarse como tal.

## Rollback, retiradas y copias

```powershell
python -m tools.publish_semantic_explorer --db .runtime/semantic-explorer/semantic_explorer.sqlite3 activate --catalog core-eg2 --release HASH_ANTERIOR
python -m tools.publish_semantic_explorer --db .runtime/semantic-explorer/semantic_explorer.sqlite3 retire --catalog core-eg2 --member ID_DEL_PLANO
python -m tools.backup --help
```

La retirada se aplica al catálogo y sobrevive a la reactivación de releases previos. Quita elegibilidad de consulta/render; no equivale a borrado físico por retención. La base opcional `semantic_explorer.sqlite3` se incluye en las copias del data dir por `tools.backup`, junto a las bases existentes. Para revertir toda la función, desactivar `VEXPLORER_EXPLORER_ENABLED` y reiniciar. No borra ni modifica revisiones de piezas.

Catálogo compartido por instancia autenticada: no usar esta versión para servir organizaciones que requieran ACL separadas dentro de una misma instancia. La política empresarial de retención/borrado físico, umbrales de relevancia y límites de operación bajo carga siguen pendientes.

## Fuentes técnicas y evidencia

La proyección centra los vectores y usa [SVD de NumPy](https://numpy.org/doc/stable/reference/generated/numpy.linalg.svd.html); corresponde a una [PCA](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html) de visualización. Las coordenadas publicadas se persisten: no se promete igualdad binaria entre plataformas con subespacios degenerados.

Los resultados del árbol final, comprobaciones de navegador y límites observados se registran en [el archivo de integración](../../team/agente_integracion_semantica.md). Las métricas y revisiones anteriores no aprueban este incremento.
