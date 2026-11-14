# Experimento de clasificación y recuperación de planos

Documento de resultados iniciales. El [índice del laboratorio](semantic-lab/README.md) enlaza auditoría, investigación, metodología, reproducción, revisión y pruebas posteriores de otros datasets. Los resultados de este documento se conservan como una corrida histórica identificada.

Trabajo en `experiment/semantic-furniture`, aislado del producto. Cuatro agentes de implementación GPT-6.1 Sol; revisión final GPT-6 Astra. Se obtuvo un clasificador y buscador experimental: **EmbeddingGemma 2 mixto, 768 dimensiones, kNN de 5 vecinos, sin PCA**. En los 18 planos reservados: **16/18 aciertos, macro-F1 0,826, balanced accuracy 0,833 y Precision@5 0,889**. La clasificación es cerrada a categorías editoriales del corpus local; no demuestra todavía generalización industrial ni similitud de costes.

## Corpus y separación

Fuente local CADBlock: 118 DXF candidatos, 117 admitidos y uno excluido por Z no nula. Los DWG equivalentes no se cuentan como muestras adicionales. Cada documento completo conserva sus vistas juntas.

| Categoría proxy | Número | Significado real |
|---|---:|---|
| sofas | 43 | Asientos tapizados, sofás, butacas y algunos objetos de la misma colección |
| simple-tables | 32 | Mesas/escritorios, frecuentemente acompañados de sillas; categoría mixta |
| beds | 21 | Camas y grupos con mesillas |
| buffets | 21 | Mostradores, carros y equipos de autoservicio/restauración; no aparadores domésticos |

Se agrupan duplicados por hashes de fuente, geometría normalizada y render, y variantes obvias mediante una heurística de nombre usada sólo para metadata. 89 grupos; 82 muestras train, 17 validation y 18 test. La heurística no prueba independencia completa entre diseños ni representa un split por fabricante/proyecto real.

Manifiesto local: `D:/Vexplorer-semantic-lab/data/core/manifest.json`.
SHA-256: `15f2448895806c85c0647da72413bfc8de39f5a6fe71d535121303f1d03f00fe`.

Los PNG 384×384 omiten textos y cotas. Nombres de archivo, rutas, categorías y grupos no entran a modelos ni features. Se eliminó también la fracción de entidades ignoradas: añadir anotaciones no debe cambiar los atributos. Las medidas de la representación geométrica son normalizadas; este canal no conserva por sí mismo el tamaño físico.

## Métodos

- Geometría determinista: proporciones, conteos, distribuciones de orientaciones y radios, longitud normalizada; StandardScaler ajustado sólo a train.
- TF-IDF del texto de observaciones geométricas. No es una descripción semántica generada por un LLM ni el descriptor completo del harness.
- MiniLM multilingüe sobre esas observaciones.
- DINOv3 ViT-S/16 sobre imágenes.
- EmbeddingGemma 2 sobre texto, imágenes y ambos; 768 y 256 dimensiones Matryoshka en los tres modos. Se ejecutaron ocho conjuntos de embeddings reales en total.
- Fusión normalizada, PCA train-only, kNN/centroides/regresión logística; KMeans/HDBSCAN como análisis de agrupación.

Selección sólo por validation: **228 configuraciones sobre 17 casos**, por lo que el 1,0 obtenido al seleccionar es vulnerable a sobreajuste y no mide generalización. Objetivo exploratorio fijado antes de los resultados aprendidos: macro-F1 ≥0,70 y balanced accuracy ≥0,75. Ambos se superaron también en test, sin reajustar tras abrirlo. No son umbrales de aceptación empresarial. La búsqueda define relevancia como misma etiqueta proxy, no igual diseño, construcción o coste.

## Resultados

Mejor configuración de cada representación individual en **validation**; la tabla no compara modelos en test. Fusión geométrica y PCA de 2/4/8 componentes también participaron en la selección completa.

| Representación | Macro-F1 | Precision@5 |
|---|---:|---:|
| Geometría determinista | 0,914 | 0,859 |
| TF-IDF geométrico | 0,488 | 0,341 |
| MiniLM texto | 0,698 | 0,435 |
| DINOv3 imagen | 0,942 | 0,859 |
| EmbeddingGemma 2 texto 768 | 0,592 | 0,447 |
| EmbeddingGemma 2 imagen 768 | 0,942 | 0,918 |
| EmbeddingGemma 2 mixto 768 | **1,000** | **0,965** |
| EmbeddingGemma 2 imagen 256 | 0,942 | 0,906 |
| EmbeddingGemma 2 mixto 256 | **1,000** | 0,953 |

Ganador congelado por macro-F1, balanced accuracy y Precision@5 de validation: mixto 768, kNN5, sin PCA. El vector contiene el plano y observaciones geométricas, no una descripción de un LLM ni todo el descriptor del harness. La variante 256 merece una futura prueba independiente por almacenamiento, pero no se eligió tras ver test. PCA2 de geometría bajó macro-F1 a 0,543; aquí no hay evidencia para usar una proyección 2D como espacio principal de búsqueda.

**Test único, 18 muestras:** macro-F1 0,826128; balanced accuracy 0,833333; Precision@5 0,888889; Hit@5 0,944444 (17/18 consultas encontraron al menos un vecino con la misma etiqueta). Exactitud simple 16/18 = 0,888889. Los vecinos se buscan sólo en las 82 muestras train.

| Etiqueta del proveedor | Casos | Clasificados con esa etiqueta |
|---|---:|---:|
| beds | 3 | 3 |
| buffets | 3 | 3 |
| simple-tables | 3 | 1 |
| sofas | 9 | 9 |

Los dos errores son un archivador de cuatro cajones (`cad_ccb44c91183858000be1`, predicho buffets) y una silla de oficina (`cad_b0556669532538a4fe0d`, predicha sofas), ambos etiquetados por el proveedor como simple-tables. La inspección visual muestra vecinos plausibles de almacenamiento y asientos. Esto evidencia ruido/ambigüedad de taxonomía; no se cambian etiquetas ni se recalculan métricas para mejorar el resultado. Un coseno alto no equivale a probabilidad ni equivalencia constructiva.

KMeans con k=5, elegido por NMI en validation sobre la representación ganadora, produce en test ARI 0,919736, NMI 0,889626 y pureza 0,944444; tamaños 9/3/2/2/2, sin ruido ni singleton. Es **análisis transductivo**: se vuelve a ajustar KMeans sobre esos 18 vectores con k congelado. La representación y k se eligieron con etiquetas de validation. No es un agrupador inductivo congelado ni un descubrimiento de categorías sin etiquetas de extremo a extremo.

Con 3 casos en tres categorías, las métricas por clase son muy inestables. Los grupos heurísticos tampoco garantizan independencia por fabricante/diseño; los ejemplos de camas muestran variantes visualmente próximas entre train y test. No se ha medido generalización a otra fuente, planos complejos, objetos desconocidos, PDFs escaneados ni despieces de producción.

## Reproducción

Desde la raíz del worktree, instalar los extras `test,semantic-lab` para el laboratorio sin modelos, y `semantic-models` para la inferencia opcional. El entorno real de esta ejecución está registrado en `D:/Vexplorer-semantic-lab/environment.json`; usa Python 3.14, torch CUDA 12.8 y un venv aislado que reutiliza paquetes globales. Una instalación nueva de torch debe corresponder al hardware disponible.

Preparar la muestra (usar un directorio de salida nuevo):

```powershell
python -m tools.semantic_lab.dataset --source 'C:/datasets/cadblock_2d' --output-dir D:/Vexplorer-semantic-lab/data/reproduction-core
```

Los modelos se ejecutan con `python -m tools.semantic_lab.encode --help`. El runner registra hash de entrada, revisión del modelo, configuración, precisión, normalización y tiempo de inferencia. El modelo original EmbeddingGemma-300M quedó excluido por acceso gated no concedido; EmbeddingGemma 2 sí se ejecuta localmente. Ningún vector OpenAI se mezcla con estos espacios.

El evaluador separa `select` y `test`:

```powershell
python -m tools.semantic_lab.evaluate select --manifest D:/Vexplorer-semantic-lab/data/core/manifest.json --output-dir D:/Vexplorer-semantic-lab/results/baseline-select --representations geometry text geometry+text --pca-components 2 4 8 --clusterers kmeans hdbscan
```

Para aprendidos, añadir `--embedding nombre=ruta.npz` por modelo. `test` exige configuración congelada, hashes idénticos y `--allow-test`; no se utiliza para volver a seleccionar. `query --help` documenta consulta por ID, vecinos y predicción con el clasificador congelado. El prototipo consulta muestras ya indexadas; no añade una pantalla ni endpoint productivo para subir planos nuevos.

Para reproducir la comparación completa con los vectores existentes, usar una salida nueva (no sobrescribir la evidencia histórica):

```powershell
python -m tools.semantic_lab.evaluate select `
  --manifest D:/Vexplorer-semantic-lab/data/core/manifest.json `
  --output-dir D:/Vexplorer-semantic-lab/results/reproduction-select `
  --embedding dino-image=D:/Vexplorer-semantic-lab/embeddings/dinov3-image-384.npz `
  --embedding minilm-text=D:/Vexplorer-semantic-lab/embeddings/minilm-text-384.npz `
  --embedding eg2-text768=D:/Vexplorer-semantic-lab/embeddings/embeddinggemma2-text-768.npz `
  --embedding eg2-image768=D:/Vexplorer-semantic-lab/embeddings/embeddinggemma2-image-768.npz `
  --embedding eg2-mixed768=D:/Vexplorer-semantic-lab/embeddings/embeddinggemma2-mixed-768.npz `
  --embedding eg2-image256=D:/Vexplorer-semantic-lab/embeddings/embeddinggemma2-image-256.npz `
  --embedding eg2-mixed256=D:/Vexplorer-semantic-lab/embeddings/embeddinggemma2-mixed-256.npz `
  --embedding eg2-text256=D:/Vexplorer-semantic-lab/embeddings/embeddinggemma2-text-256.npz `
  --representations geometry text geometry+text embeddings geometry+embeddings `
  --classifiers knn centroid logreg --clusterers kmeans hdbscan `
  --cluster-counts 2 3 4 5 --pca-components 2 4 8 --neighbors 5 --retrieval-k 5 --seed 0
```

El evaluador actual rechazará el config histórico al intentar abrir un test nuevo porque su informe es anterior al guard. Para reproducir una corrida de punta a punta, usar la pareja de informes recién generada y otra salida; eso es reproducción, no un nuevo test independiente. No se hizo tal repetición para este informe.

Ejemplo de consulta del índice final existente, desde el worktree:

```powershell
python -m tools.semantic_lab.query --index-npz D:/Vexplorer-semantic-lab/results/final-test/query-index.npz --index-json D:/Vexplorer-semantic-lab/results/final-test/query-index.json --frozen-config D:/Vexplorer-semantic-lab/results/all-select/frozen-config.json --sample-id cad_b0556669532538a4fe0d --k 5
```

Se conserva la selección completa en [validation-report.json](experiments/semantic-lab-2026-11-14/validation-report.json), el [config congelado](experiments/semantic-lab-2026-11-14/frozen-config.json), el [test original](experiments/semantic-lab-2026-11-14/test-report.json) y un [resumen con procedencia de modelos, matriz y errores](experiments/semantic-lab-2026-11-14/results-summary.json). Los JSON históricos se conservan sin reinterpretarlos como ejecuciones posteriores de un evaluador modificado.

Artefactos locales adicionales: `D:/Vexplorer-semantic-lab/results/final-test/{queries.json,diagnostics.json,confusion.png,neighbor-examples.png}` y `D:/Vexplorer-semantic-lab/results/validation-comparison.png`. Los gráficos de vecinos se inspeccionaron visualmente y muestran tanto aciertos como los dos errores. Los datos CAD y renders no se añaden a Git.

EmbeddingGemma 2 revisión `f9972ac22e696a105c482202646979e33e4b5a1e`, inferencia BF16 y normalización final L2 float32. El NPZ ganador tiene SHA-256 `e7b31ec8580972999525f367934a0a85550bd7c503df65dfc7c363edae8ba4a5`. Codificar las 117 muestras mixtas tardó 17,815 s en esta GPU; excluye descarga/carga del modelo y no representa latencia productiva completa. Es un modelo distinto de EmbeddingGemma-300M: véase [ficha oficial de EmbeddingGemma 2](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2).

## Comparación constructiva complementaria

`tools.semantic_lab.components.compare_components` consume los descriptores V2/V3 existentes. Empareja multiconjuntos por transporte óptimo, dimensiones, cantidades, roles y materiales conocidos, con cobertura separada. No expande millones de ocurrencias físicas. Las cantidades ausentes se representan como peso de observación y se identifican explícitamente como no físicas.

Controles sintéticos propios: exacto/reordenado 1,0; ancho del soporte 550→200 mm 0,884298; espesor 18→36 mm 0,8125; material distinto 0,9. Pesos fijados manualmente, no aprendidos ni calibrados como equivalencia de fabricación. Este componente permanece fuera del runtime del producto y no produce precios.

## Revisión y alcance siguiente

GPT-6 Astra verificó que el config utilizado coincide con el ganador de validation y que los hashes reales coinciden. Detectó que el guard inicial no enlazaba criptográficamente config y selección: se añadió un control para futuras corridas, pero la ejecución histórica dependió de la disciplina de congelación y de esa comprobación independiente. Un guard local no impide que una persona edite todos los artefactos o abra test en otro directorio.

También detectó un caso de afinidad cero en el comparador de componentes: se corrigió para maximizar primero la masa compatible y después la afinidad, conservando diferencias explicables. Las métricas del modelo ganador no se recalcularon ni se seleccionó otro método a raíz de la revisión.

Verificación final de coordinación tras los ajustes: **466 tests aprobados en 60,66 s**, Ruff sin hallazgos, `compileall` correcto y `git diff --check` correcto. Se ejecutó también la consulta CLI anterior y se verificaron sus cinco vecinos y predicción. [Versiones del entorno](experiments/semantic-lab-2026-11-14/environment.json) y [controles sintéticos de componentes](experiments/semantic-lab-2026-11-14/components-control.json) acompañan la evidencia.

**Dictamen final GPT-6 Astra del experimento inicial:** aprobado como spike experimental aislado, sin hallazgos bloqueantes pendientes. Hay evidencia de recuperación coherente y clasificación cerrada según las cuatro categorías proxy. No se considera apto todavía para clasificación industrial, comparables de coste ni integración productiva. Se corrigió también la declaración directa de SciPy y una cifra de la tabla DINOv3 durante revisión. El cierre inicial fue local; posteriormente el usuario autorizó organizar documentación y hacer commit/push de la rama experimental. Esa publicación no implica merge ni despliegue.

Para pasar a mobiliario propio, el siguiente experimento debe usar una taxonomía revisada, pares de similitud juzgados por técnicos y separación por proyecto/fabricante. El embedding visual sirve para recuperar candidatos; la comparación de BOM/materiales/espesores/medidas debe reordenarlos con información real del harness. Precios necesitan además históricos comparables y validación específica: estas métricas no prueban que los vecinos cuesten parecido. El código de producto y los contratos permanecen intactos.
