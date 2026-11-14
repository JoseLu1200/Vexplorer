# Reproducción, uso local y artefactos

Ejecutar los comandos desde la raíz de la rama `experiment/semantic-furniture`. La [metodología](METODOLOGIA.md) define qué mide cada fase. Esta guía no inicia ni despliega el producto.

## Entorno

El experimento observado usó Windows, Python 3.14.2, Ryzen 9 9955HX, 32 GB de RAM y RTX 5070 Ti Laptop de 12 GB. Las versiones exactas están en [environment.json](../experiments/semantic-lab-2026-11-14/environment.json): NumPy 2.3.5, SciPy 1.17.0, scikit-learn 1.8.0, torch 2.10.0+cu128, Transformers 5.23.0, Sentence Transformers 6.3.0, huggingface-hub 1.33.0, ezdxf 1.4.5 y Pillow 12.0.0.

El entorno de inferencia real está en `D:/Vexplorer-semantic-lab/venv` y reutiliza torch global mediante `--system-site-packages`. Se hizo así por espacio en disco; no es una receta de instalación aislada exacta. No se guardó una imagen de sistema ni un lock completo de todas las dependencias transitivas. En otra máquina deben conservarse las revisiones de modelos y registrarse las versiones efectivas; GPU, kernels o versiones distintas pueden variar resultados y tiempos.

Instalación ordinaria sin inferencia de modelos:

```powershell
python -m venv .venv-semantic
.\.venv-semantic\Scripts\python.exe -m pip install -e '.[test,semantic-lab]'
```

Para inferencia, instalar además el extra `semantic-models`; elegir una distribución de torch compatible con el hardware disponible antes de ejecutar GPU. El extra declara librerías, no un controlador CUDA ni acceso automático a modelos restringidos.

```powershell
.\.venv-semantic\Scripts\python.exe -m pip install -e '.[semantic-models]'
```

Los tests del laboratorio no descargan pesos ni requieren GPU. La verificación del experimento se ejecutó con el Python global indicado en el registro; los modelos usaron el venv de D:. Ambos entornos y sus funciones se distinguieron en los informes.

## Entradas y directorios

| Ruta local usada | Contenido | ¿Se incluye en Git? |
|---|---|---|
| `1hack/cadblock_2d` | DXF/DWG y metadata de terceros. | No |
| `D:/Vexplorer-semantic-lab/data/core` | Manifiesto, renders y QA de 117 muestras. | No |
| `D:/Vexplorer-semantic-lab/embeddings` | Ocho NPZ y sus JSON de procedencia. | No |
| `D:/Vexplorer-semantic-lab/hf-cache`, `hf-home` | Pesos y cachés auxiliares. | No |
| `D:/Vexplorer-semantic-lab/results/all-select` | Selección original de 228 configuraciones e índice de validation. | Sólo JSON resumidos/copias explícitas |
| `D:/Vexplorer-semantic-lab/results/final-test` | Test original, índice, consultas, diagnósticos y gráficos. | Sólo JSON resumidos/copias explícitas |
| `D:/Vexplorer-semantic-lab/cross-dataset` | Inventario y pruebas posteriores de otras fuentes y de la app. | Según el inventario de sus informes; sin entradas de terceros |
| `docs/experiments/semantic-lab-2026-11-14` | Evidencia pequeña de la corrida inicial. | Sí |

El manifiesto contiene rutas locales y su hash depende de sus bytes exactos. Mover entradas y reescribir rutas cambia el hash: no se debe reutilizar entonces un config congelado como si correspondiera al mismo manifiesto. Los archivos NPZ externos no se reconstruyen sólo a partir del resumen JSON.

## Preparar un corpus nuevo

En la máquina original, el origen fue el directorio `cadblock_2d` junto al repositorio. Cambiar `$SemanticCorpus` por el directorio autorizado que conserve la estructura esperada. Usar una salida nueva para no sobrescribir evidencia histórica.

```powershell
$SemanticCorpus = 'C:/datasets/cadblock_2d'
$SemanticRun = 'D:/Vexplorer-semantic-reproduction'
$SemanticPython = '.\.venv-semantic\Scripts\python.exe'
& $SemanticPython -m tools.semantic_lab.dataset --source $SemanticCorpus --output-dir "$SemanticRun/data/core"
```

El preparador crea el manifiesto, su SHA-256 y renders. Por defecto selecciona las cuatro categorías del experimento, tamaño 384 y semilla 20261114. `--categories` acepta una lista separada por comas. Revisar exclusiones y distribución antes de codificar o evaluar; no suponer que otra descarga tiene idéntico contenido.

## Codificar con EmbeddingGemma 2

```powershell
& $SemanticPython -m tools.semantic_lab.encode `
  --manifest "$SemanticRun/data/core/manifest.json" `
  --model embeddinggemma2 --mode mixed --precision bfloat16 --device cuda `
  --output "$SemanticRun/embeddings/embeddinggemma2-mixed-768.npz" `
  --cache-dir "$SemanticRun/model-cache"
```

En CPU usar `--device cpu --precision float32`. Para Matryoshka 256, añadir `--truncate-dim 256` y elegir otro nombre de salida. Los modos alternativos son `image` y `text`; los otros modelos son `dinov3` (sólo imagen) y `minilm` (sólo texto).

El adaptador DINOv3 exige un snapshot completo existente en `~/.cache/huggingface/hub`; su implementación no descarga pesos ni usa `--cache-dir` para localizar esos pesos. Este parámetro sí participa en el almacenamiento del runner. DINOv3 se ejecutó aprovechando una copia local ya disponible. Las implementaciones Sentence Transformers tienen su propia resolución de caché indicada en el código. La CLI no expone un pin de revisión: comprobar la revisión realmente registrada frente a la esperada es necesario para una reproducción estricta.

EmbeddingGemma-300M original no forma parte del runner: el acceso no estaba concedido en la sesión. No se intentó eludir esa restricción. EmbeddingGemma 2 sí pudo ejecutarse. Los adaptadores usan `trust_remote_code=False`.

Verificar por cada salida: 117 filas si se reproduce el mismo corpus; IDs únicos; dimensión esperada; valores finitos; norma unitaria; hash del manifiesto y revisión. El runner ya valida estos invariantes antes de persistir. Un fallo CLI queda registrado en el JSON adjunto con tipo y mensaje; no es una ejecución válida del modelo.

## Seleccionar, congelar y evaluar

La invocación completa de las 228 configuraciones está en [Resultados iniciales, reproducción](../SEMANTIC_LAB_2026-11-14.md). Reutiliza los ocho NPZ, tres bases, fusiones, tres clasificadores y PCA 2/4/8. Los tiempos de codificación excluyen carga/descarga del modelo.

Para una prueba mínima del método fijo, sin repetir la búsqueda completa:

```powershell
& $SemanticPython -m tools.semantic_lab.evaluate select `
  --manifest "$SemanticRun/data/core/manifest.json" `
  --output-dir "$SemanticRun/results/select" `
  --embedding "eg2-mixed768=$SemanticRun/embeddings/embeddinggemma2-mixed-768.npz" `
  --representations embeddings --classifiers knn `
  --clusterers kmeans --cluster-counts 5 --neighbors 5 --retrieval-k 5 --seed 0
```

Esto no reproduce la competición de 228 candidatos: registra una configuración preseleccionada y sus resultados de validation. Para abrir test, la salida debe contener la pareja recién generada `validation-report.json` y `frozen-config.json`, y los hashes deben coincidir:

```powershell
& $SemanticPython -m tools.semantic_lab.evaluate test `
  --manifest "$SemanticRun/data/core/manifest.json" `
  --frozen-config "$SemanticRun/results/select/frozen-config.json" `
  --output-dir "$SemanticRun/results/test" `
  --embedding "eg2-mixed768=$SemanticRun/embeddings/embeddinggemma2-mixed-768.npz" `
  --allow-test
```

El informe histórico original se generó antes del nuevo guard y no se modificó. El evaluador actual rechazará ese config histórico para una nueva apertura por falta del enlace de hash en su informe. No añadirlo manualmente para aparentar que existió. Una reproducción posterior con nuevos informes no constituye un segundo conjunto de prueba independiente.

## Consultar lo ya calculado

Ejemplo real sobre el índice original:

```powershell
python -m tools.semantic_lab.query `
  --index-npz D:/Vexplorer-semantic-lab/results/final-test/query-index.npz `
  --index-json D:/Vexplorer-semantic-lab/results/final-test/query-index.json `
  --frozen-config D:/Vexplorer-semantic-lab/results/all-select/frozen-config.json `
  --sample-id cad_b0556669532538a4fe0d --k 5
```

Devuelve los IDs de vecinos train, sus etiquetas proxy, cosenos, contribución por modalidad y predicción. El ejemplo es una silla de oficina que el proveedor incluyó en `simple-tables`; el clasificador devuelve `sofas` y vecinos de asientos.

`query` admite IDs presentes en el índice, no un archivo nuevo ni una consulta de lenguaje natural. No persiste un pipeline listo para inferir cualquier plano desde un endpoint. Para nuevos documentos hay que extraer/codificar y construir explícitamente su experimento o integrar esa funcionalidad en otra tarea.

## Comparador de componentes y verificaciones

```powershell
python -m tools.semantic_lab.components control --output D:/Vexplorer-semantic-reproduction/components-control.json
python -m pytest -q
python -m ruff check tools/semantic_lab tests/test_semantic_lab_*.py
python -m compileall -q tools/semantic_lab
git diff --check
```

Si el shell no expande el patrón de tests para Ruff, enumerar los archivos o pasar el directorio `tests` según el alcance deseado. `git diff --check` debe ejecutarse también con `--cached` una vez preparado el commit para cubrir todos los archivos añadidos.

El control de componentes es sintético y no llama a un LLM. La última suite inicial aprobó 466 tests; las verificaciones posteriores de los probes se registran en sus informes y en el cierre de publicación, sin sobrescribir esa cifra histórica.

## Problemas observados y resolución

| Incidencia | Acción aplicada |
|---|---|
| Python/modelos disponibles en entornos distintos | Venv de inferencia separado y versiones efectivas registradas. |
| Imports de Transformers incompatibles con huggingface-hub antiguo | Actualización de dependencias compatibles en el venv, con versiones registradas. |
| EmbeddingGemma original restringido | Se registró falta de acceso; se ejecutó EG2 disponible. |
| Normas BF16 aproximadamente 0,996–1,004 | Normalización final float32 y regeneración de los ocho NPZ antes de evaluar. |
| Truncado solicitado a un modelo sin contrato Matryoshka | Se limita a dimensiones declaradas de EG2. |
| Config local editable tras selección | Hash canónico y cotejo con el informe para corridas nuevas; evidencia antigua preservada. |
| Unicode en rutas de Windows | Lectura/escritura explícita UTF-8 en JSON y documentación. |

No se reabrió el test inicial ni se reajustó su ganador para corregir documentación o controles de ejecución.
