# Metodología e implementación del laboratorio

Este documento describe lo que ejecuta el código del experimento inicial, no una arquitectura productiva ya integrada. Los resultados están en el [informe inicial](../SEMANTIC_LAB_2026-11-14.md); las fuentes externas en [Investigación](INVESTIGACION_SOTA.md).

## 1. Unidad de análisis y separación

La unidad es un documento DXF completo, que puede contener varias vistas del mismo objeto e incluso una composición de varios muebles. Las vistas permanecen juntas al particionar. No se interpreta cada vista como una pieza o una ocurrencia física.

El manifiesto usa `schema_version=1`, `metadata` y `samples`. Cada muestra aporta:

| Campo | Uso |
|---|---|
| `id` | Identidad estable para enlazar resultados; no entrada al encoder. |
| `source_path`, `image_path` | Localización de entradas y render; el modelo recibe contenido, no rutas. |
| `label`, `label_source` | Etiqueta editorial para evaluación y entrenamiento del clasificador; no entrada al encoder. |
| `group_id` | Grupo previo a la partición; evita separar duplicados/variantes detectados. |
| `split` | `train`, `validation` o `test`. |
| `features` | Atributos geométricos numéricos finitos. |
| `text` | Observaciones geométricas generadas determinísticamente. |

El preparador une coincidencias por hash del archivo, firma geométrica normalizada y hash del render, además de variantes nominales obvias. El nombre sólo interviene en agrupación/metadata. Después asigna grupos completos a particiones con semilla `20261114`. El evaluador rechaza IDs duplicados y un mismo grupo presente en dos splits.

Esto reduce fugas detectables; no garantiza que diseños visualmente emparentados, fabricantes o proyectos estén separados. Tampoco se conoce si los modelos preentrenados vieron diseños públicos relacionados durante su entrenamiento original.

## 2. Representación geométrica y render

El extractor experimental trabaja sobre modelspace, expande bloques y utiliza líneas, polilíneas y curvas soportadas por su conversión a paths. Las curvas se discretizan para representar forma, no para certificar metrología. Rechaza geometría con Z no nula, geometría degenerada y archivos sin primitivas utilizables.

La normalización traslada el mínimo de la envolvente al origen y divide ambos ejes por el mayor lado. Por ello conserva proporciones y pierde escala física absoluta. No normaliza rotaciones arbitrarias. Genera PNG de 384×384, monocromo, con margen y ancho de trazo constante. Los textos, atributos, cotas y otros elementos ignorados no forman parte del render ni del texto de entrada.

Los 27 atributos numéricos son:

- Seis globales: ancho/alto normalizados, logaritmo de aspecto, `log1p` de paths y segmentos, longitud total normalizada.
- Ocho fracciones por tipo de primitiva.
- Ocho intervalos de orientación ponderados por longitud.
- Cinco intervalos de distancia radial ponderados por longitud.

El texto contiene sólo los seis globales con formato fijo. No es una descripción semántica redactada por un LLM ni una serialización completa de BOM, materiales o dimensiones del harness. Se retiró el porcentaje de entidades ignoradas porque añadir anotaciones podía cambiarlo sin cambiar la forma.

## 3. Modelos y formatos de salida

| Modelo | Entrada ejecutada | Dimensiones |
|---|---|---:|
| DINOv3 ViT-S/16 | Render | 384 |
| MiniLM multilingüe L12 | Texto geométrico | 384 |
| EmbeddingGemma 2 | Texto | 768 y 256 |
| EmbeddingGemma 2 | Render | 768 y 256 |
| EmbeddingGemma 2 | Texto + render en una entrada multimodal | 768 y 256 |

Los pesos preentrenados no se ajustaron con el corpus. Se entrenaron únicamente los clasificadores y transformaciones posteriores indicados abajo. La codificación independiente de las 117 entradas, incluido test, no utilizó sus etiquetas; el ajuste y la selección no utilizaron sus vectores test hasta la fase reservada.

El runner comprueba IDs únicos, número de filas, dimensión, finitud y norma no nula. Normaliza las filas en float32 antes de guardar NPZ (`ids`, `embeddings`, sin pickle). Un JSON adjunto registra modelo, revisión real, precisión, modo, dimensión, hash del manifiesto, hashes de entradas ordenadas, versión del runner, normalización, hash del NPZ y tiempos. La caché distingue estas identidades.

EmbeddingGemma 2 admite truncado nativo a 128/256/512/768; se probaron 256 y 768. Se normaliza de nuevo tras truncar. No se aplica ese truncado arbitrariamente a DINOv3 o MiniLM. DINOv3 usa media de `last_hidden_state` tal como lo devuelve el adaptador; no se optimizó pooling ni se entrenó un modelo específico para dibujos.

Las versiones y precisiones efectivamente usadas están en [environment.json](../experiments/semantic-lab-2026-11-14/environment.json) y [results-summary.json](../experiments/semantic-lab-2026-11-14/results-summary.json). Un coseno de 0,95 no expresa un 95 % de probabilidad.

## 4. Transformaciones, fusión y clasificadores

Todas las transformaciones con parámetros se ajustan exclusivamente en train:

1. Geometría: `StandardScaler`; PCA opcional; normalización L2.
2. Texto: `TfidfVectorizer`; PCA opcional; normalización L2.
3. Embeddings: PCA opcional sobre los vectores train; normalización L2.
4. Fusión: concatenación de modalidades normalizadas con peso 1 para cada una; normalización L2 del resultado.

PCA se aplica por modalidad antes de concatenar. No se ajusta sobre validation/test ni se confunde una proyección de dos dimensiones con un clasificador semántico. Las variantes fueron sin PCA y con 2, 4 u 8 componentes.

Clasificadores:

- kNN: cinco vecinos, distancia coseno y voto ponderado por distancia.
- Centroide: media por clase, normalizada; predicción por mayor coseno.
- Regresión logística: clases balanceadas, máximo 2.000 iteraciones y semilla 0.

El clasificador es cerrado: siempre escoge una de las clases conocidas. No se implementó rechazo calibrado de objetos desconocidos, detección fuera de dominio ni una probabilidad comercialmente validada.

## 5. Selección y test

La búsqueda inicial contiene 19 representaciones: tres bases (`geometry`, `text`, `geometry+text`), ocho espacios aprendidos solos y sus ocho fusiones con geometría. Con cuatro opciones de PCA y tres clasificadores, son **228 configuraciones**. Todas terminaron sin error en esa corrida.

Se selecciona por macro-F1, balanced accuracy y Precision@5 de validation. Con sólo 17 ejemplos y tantos candidatos, la elección es inestable. Los objetivos exploratorios macro-F1 ≥0,70 y balanced accuracy ≥0,75 se fijaron antes de obtener resultados aprendidos; no son criterios industriales.

El ganador fue Gemma 2 mixto768 + kNN5, sin PCA. El entrenamiento final siguió usando las 82 muestras train; no se incorporaron las 17 de validation. Se abrió una vez el test de 18 muestras y no se cambió ganador, etiqueta ni umbral después de ver los errores.

La versión inicial comprobaba hash de manifiesto/NPZ y pedía `--allow-test`; impedía sobrescribir un `test-report.json` existente en la misma salida. Astra detectó que el config podía editarse sin compararlo con el informe de selección. Ahora `select` registra su hash canónico y `test` exige el informe adyacente y verifica hash, ganador y clustering. Los informes históricos se conservan sin añadirles ese control a posteriori. Astra cotejó manualmente la selección histórica y sus hashes.

Estos controles locales detectan cambios accidentales. No impiden que alguien cambie todos los artefactos, cree otra salida o modifique código. La separación experimental sigue siendo una disciplina documentada, no un recinto criptográfico inviolable.

## 6. Métricas y su significado

| Métrica | Definición usada | Límite |
|---|---|---|
| Macro-F1 | Media del F1 por clase. | Cada clase pesa igual, pero con tres casos una clase tiene gran variación. |
| Balanced accuracy | Media del recall por clase. | No es exactitud global ni calibración probabilística. |
| Exactitud global | Aciertos / consultas. | Puede ocultar desequilibrio de clases. |
| Precision@5 | Media de la fracción de cinco vecinos con la misma etiqueta editorial. | No mide igualdad de diseño ni de coste. |
| Hit@5 | Fracción de consultas con al menos un vecino de igual etiqueta. | No debe llamarse Recall@5: no divide por todos los relevantes. |
| Cobertura de retrieval | Consultas evaluadas / todas las consultas; sólo se puntúan si existe relevante en train. | Debe acompañar las métricas para detectar exclusiones. |
| ARI y NMI | Correspondencia de asignaciones de cluster con etiquetas. | Incluyen la asignación de ruido tal como se reporta. |
| Pureza | Fracción mayoritaria por cluster, sobre asignados. | Puede aumentar al excluir ruido o fragmentar en clusters pequeños. |

Retrieval usa exclusivamente train como referencia, excluye el propio ID y desempata por ID. El índice de consulta guarda train más las consultas de la fase; la búsqueda restringe candidatos al split de referencia. `query` puede predecir reconstruyendo el clasificador desde los vectores/etiquetas train almacenados. Su etiqueta de consulta se devuelve como metadata de evaluación; no se utiliza para predecirla.

## 7. Agrupación

Tras elegir la representación ganadora se probaron ocho configuraciones de agrupación, no ocho por cada uno de los 228 clasificadores. KMeans usó k=2/3/4/5, semilla 0 y 20 inicializaciones; HDBSCAN usó tamaño mínimo de cluster 2/3/4/5. En HDBSCAN ese parámetro no significa número de clusters.

En validation, KMeans5 logró NMI 0,877 y ARI 0,821. HDBSCAN con mínimo 2 alcanzó pureza 1,0, pero dejó dos de 17 muestras como ruido: cobertura 0,882 y NMI 0,820. Con mínimo 5 dejó todas como ruido. Por eso no basta con citar la pureza máxima.

KMeans5 se eligió por NMI, cobertura y menos singleton. Después se volvió a ajustar sobre los 18 vectores test con ese hiperparámetro congelado. Este resultado es **transductivo**. Tanto representación como k se eligieron utilizando etiquetas de validation; no demuestra descubrimiento semántico completamente no supervisado ni un clasificador inductivo de clusters listo para nuevas entradas.

## 8. Comparación constructiva

`compare_components` consume `FurnitureDescriptorV2` o `FurnitureDescriptorV3`. No se conectó a la búsqueda de Gemma ni se entrenó con relevancia humana. Es una segunda señal explicable para una integración futura.

Empareja multiconjuntos mediante transporte óptimo: primero maximiza masa compatible y después afinidad. No expande una fila con cantidad grande en millones de objetos. Roles conocidos incompatibles no se emparejan. La orientación de soportes se conserva; largo/ancho se canonicalizan sólo cuando el rol permite intercambio de ejes (`tabletop` o rol desconocido V2).

La similitud entre dimensiones conocidas es `exp(-abs(log(a/b))/0.5)`. Pesos manuales: rol 0,15; cantidad 0,10; largo 0,20; ancho 0,20; espesor 0,25; material 0,10. Los valores desconocidos reducen cobertura y contribución; no se rellenan con dimensiones típicas. Una cantidad V2 ausente se usa como un peso de observación para el algoritmo y se identifica explícitamente como no física.

Los controles sintéticos muestran sensibilidad a ancho, espesor y material, e invariancia al orden de componentes. No demuestran exactitud sobre despieces reales ni equivalencia de fabricación. Los resultados completos están en [components-control.json](../experiments/semantic-lab-2026-11-14/components-control.json).
