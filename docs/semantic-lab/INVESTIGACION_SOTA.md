# Investigación de representaciones para recuperación de planos

Fecha de corte: 2026-11-14.

Este documento registra la investigación que orientó el laboratorio semántico de Vexplorer. Separa fuentes consultadas, modelos ejecutados y líneas pendientes. Los benchmarks publicados por los autores describen otros corpus; no miden el rendimiento sobre planos de mobiliario de CADBlock ni acreditan equivalencia constructiva, económica o industrial.

## Pregunta experimental

El laboratorio estudió si una representación local podía recuperar y clasificar planos visualmente coherentes sin introducir la categoría, la ruta, el nombre de archivo ni el grupo de duplicados en la entrada del modelo.

El corpus congelado contiene 117 DXF admitidos, cuatro categorías editoriales usadas como proxy y 89 grupos. Los renders de 384 × 384 píxeles omiten texto y cotas. El texto de entrada procede sólo de observaciones geométricas. El manifiesto tiene SHA-256 `15f2448895806c85c0647da72413bfc8de39f5a6fe71d535121303f1d03f00fe`.

La evaluación comparó geometría determinista, TF-IDF, MiniLM, DINOv3 y EmbeddingGemma 2. El evaluador ajustó escalado y PCA sólo con train, seleccionó en validation y abrió test una vez después de congelar la configuración.

## Estado de cada vía

| Vía | Estado | Uso en el laboratorio |
|---|---|---|
| EmbeddingGemma 2 | Ejecutada | Texto, imagen y mezcla texto-imagen; 768d y 256d |
| DINOv3 ViT-S/16 | Ejecutada | Imagen, 384d |
| MiniLM multilingüe | Ejecutada | Texto, 384d; control ligero |
| EmbeddingGemma 300M original | Investigada, no ejecutada | El repositorio exige aprobación y la cuenta local recibió `ACCESS_DENIED` |
| Qwen3-VL-Embedding-2B | Investigada, no ejecutada | Alternativa multimodal de mayor tamaño; no hacía falta descargar otro checkpoint para responder la primera pregunta |
| SigLIP 2 | Investigada, no ejecutada | Alternativa imagen-texto pública; el presupuesto local favoreció una comparación más corta con modelos ya descargados |
| PCA | Ejecutada | Reducción ajustada sólo en train |
| HDBSCAN y KMeans | Ejecutadas | Análisis de agrupación, separado de clasificación y retrieval |
| UMAP | Investigada, no ejecutada | Candidata para visualización y experimentos posteriores; no se usó como prueba de separabilidad |
| Metric learning supervisado | Investigado, no ejecutado | Requiere pares o etiquetas de similitud más fiables que las cuatro carpetas proxy |

## EmbeddingGemma original y EmbeddingGemma 2

### EmbeddingGemma 300M

Google describe la primera EmbeddingGemma como un modelo de texto multilingüe de unos 300 millones de parámetros, contexto de 2K tokens y salida Matryoshka. No contiene encoder visual. La documentación oficial conserva la comparación con la versión actual en [EmbeddingGemma](https://ai.google.dev/gemma/docs/embeddinggemma); el checkpoint vive en [google/embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m).

La ficha de Hugging Face marca el repositorio como gated con aprobación manual. La cuenta local pudo listar el repositorio, pero la lectura de `config.json` y el dry-run de descarga devolvieron acceso denegado. El laboratorio no simuló el modelo ni usó un fork.

### EmbeddingGemma 2

EmbeddingGemma 2 es otro modelo. Google lo publicó con licencia Apache 2.0 y una arquitectura multimodal compartida para texto, imagen, vídeo y audio. La [ficha oficial de Google](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2), el [checkpoint de Hugging Face](https://huggingface.co/google/embeddinggemma-2) y la [documentación de Transformers](https://huggingface.co/docs/transformers/model_doc/embedding_gemma2) describen:

- 744,4 millones de parámetros en el checkpoint completo;
- 270M efectivos para texto, 440M para texto más visión y 740M para todas las modalidades;
- vectores nativos de 768 dimensiones;
- truncado Matryoshka declarado a 512, 256 y 128 dimensiones;
- contexto de 8.192 tokens;
- uso de `bfloat16` o `float32`; Google desaconseja `float16` por riesgo de NaN o degradación silenciosa;
- Sentence Transformers 6.1 o posterior para el orden correcto de entradas multimodales.

La cifra 440M corresponde a texto más visión, no al checkpoint completo. El archivo `model.safetensors` descargado ocupa cerca de 1,5 GB porque contiene todas las torres.

El laboratorio eligió EG2 por tres razones concretas. Primero, una sola revisión produce texto, imagen y mezcla en el mismo espacio de 768d. Segundo, la RTX local admite BF16. Tercero, el modelo permite comparar 768d y 256d sin entrenar PCA ni otro proyector.

El runner desactivó audio en imagen y mezcla, y desactivó audio y visión en texto. Cargó el modelo con `trust_remote_code=False`. Para mezcla insertó el marcador `<|image|>` junto al descriptor geométrico. Tras el forward BF16, normalizó cada fila en float32. Esta normalización corrigió normas observadas entre 0,996 y 1,004 antes del postproceso.

Revisión ejecutada: `f9972ac22e696a105c482202646979e33e4b5a1e`.

## Controles visuales y textuales

### DINOv3

Meta presenta DINOv3 como una familia de backbones visuales auto-supervisados. La [ficha ViT-S/16](https://huggingface.co/facebook/dinov3-vits16-pretrain-lvd1689m), el [artículo](https://arxiv.org/abs/2508.10104) y el [repositorio de autores](https://github.com/facebookresearch/dinov3) documentan 21,6M parámetros, patch 16 y salida de 384 dimensiones para la variante pequeña.

DINOv3 no comparte espacio con texto. Sirve como control visual congelado: si sus vecinos superan a los embeddings textuales, el render contiene señal útil aun sin etiquetas ni OCR. El checkpoint actual está gated, pero la máquina ya conservaba una revisión completa con configuración y pesos. El laboratorio la cargó en modo local, sin descargar ni ejecutar código remoto.

Revisión ejecutada: `114c1379950215c8b35dfcd4e90a5c251dde0d32`.

El runner usó `DINOv3ViTImageProcessor`, lotes de 16 y media de `last_hidden_state` seguida de normalización L2. Esa media incluye los tokens que devuelve el adaptador; el experimento no comparó CLS, patch pooling ni una cabeza ajustada al dominio. No atribuyó Matryoshka a DINOv3.

### MiniLM multilingüe

[paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) proporciona un control textual pequeño de 384 dimensiones. El laboratorio lo aplicó al texto neutral derivado de geometría. Este texto no contiene una descripción humana rica ni el descriptor completo de Vexplorer.

Revisión ejecutada: `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`.

## Qwen3-VL-Embedding como alternativa

Qwen publicó [Qwen3-VL-Embedding-2B](https://huggingface.co/Qwen/Qwen3-VL-Embedding-2B), el [informe técnico](https://arxiv.org/abs/2601.04720) y el [repositorio oficial](https://github.com/QwenLM/Qwen3-VL-Embedding). El modelo acepta texto, imagen, vídeo y combinaciones; expone hasta 2.048 dimensiones y declara soporte Matryoshka.

La alternativa merece una prueba posterior por su diseño específico de retrieval multimodal y por la disponibilidad de un reranker compatible. El laboratorio no la ejecutó por cuatro motivos:

1. el checkpoint tiene 2.127,5M parámetros, casi tres veces EG2 completo;
2. no estaba en caché;
3. EG2 ya cubría las tres modalidades necesarias con menor descarga y menor memoria;
4. el corpus de 117 muestras no justificaba ampliar la búsqueda de modelos después de responder la pregunta inicial.

Los resultados MMEB publicados por Qwen no permiten anticipar su orden sobre dibujos lineales de mobiliario. Una comparación válida necesita la misma separación por grupos, los mismos renders y el mismo protocolo de validation/test.

## Recuperación de CAD y planos técnicos

La literatura próxima confirma que el dominio necesita algo más que un embedding visual genérico:

- [BLUEPRINT](https://arxiv.org/abs/2602.13345) combina detección de regiones, OCR restringido, normalización de identificadores, recuperación léxica y densa, y reranking sobre archivos de ingeniería. Su tarea incluye documentos complejos y metadatos; no equivale a clasificar siluetas de mobiliario.
- [Blueprint2CAD](https://arxiv.org/abs/2611.02433) evalúa correspondencia entre dibujos ortográficos y renders de piezas 3D. Sus autores identifican el cambio de punto de vista como un cuello de botella. El laboratorio de Vexplorer usa una taxonomía de carpetas y no dispone de pares dibujo-modelo comparables.
- [CADSketchNet](https://arxiv.org/abs/2107.06212) estudia recuperación de modelos CAD 3D desde bocetos. Aporta un precedente para aprendizaje de métrica entre dos dominios visuales, pero trabaja con piezas mecánicas y galerías 3D.
- [Drawing2CAD](https://github.com/lllssc/Drawing2CAD) aprende generación de programas CAD desde dibujos vectoriales multivista. Su objetivo es reconstrucción, no búsqueda de muebles históricos.
- [CoLIBRi](https://github.com/ScaDS/CoLIBRi) publica una arquitectura de recuperación para dibujos de fabricación con OCR, segmentación de formas, CLIP y metadatos. El repositorio sirve como referencia de sistema, no como benchmark transferible a este corpus.

Estas fuentes favorecen una arquitectura híbrida para Vexplorer: el embedding visual recupera candidatos; geometría, componentes, materiales, espesores y cantidades reordenan y explican los vecinos. OCR y title blocks sólo deben entrar cuando el caso de uso permita esa información. Los renders geometry-only del experimento los excluyeron de forma deliberada.

## Reducción, agrupación y aprendizaje de métrica

### PCA

[PCA de scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html) aprende componentes a partir de la varianza de los datos. El laboratorio ajustó escalado y PCA sólo en train. PCA a dos componentes redujo el macro-F1 de geometría a 0,543 en validation; esa ejecución no respalda usar una proyección 2D como índice principal. Una gráfica legible tampoco demuestra clusters útiles.

### UMAP

El [artículo de UMAP](https://arxiv.org/abs/1802.03426) y la [documentación de parámetros](https://umap-learn.readthedocs.io/en/latest/parameters.html) explican que `n_neighbors`, `min_dist` y la métrica cambian la estructura visible. UMAP acepta distancia coseno y puede transformar puntos nuevos después de ajustar sobre train.

UMAP queda como herramienta de inspección, con semilla y configuración registradas. Si se usa para clasificación o clustering, debe ajustarse sólo en train y evaluarse como cualquier otra transformación. Ajustarlo sobre todo el corpus antes de medir contaminaría validation y test.

### HDBSCAN

[HDBSCAN en scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html) integra particiones DBSCAN sobre distintas escalas y permite marcar ruido mediante `min_cluster_size`. La [documentación de predicción](https://hdbscan.readthedocs.io/en/latest/prediction_tutorial.html) aclara que el método es transductivo y que asignar puntos nuevos a una jerarquía congelada es una aproximación.

El laboratorio comparó HDBSCAN con KMeans y reportó cobertura, ruido y singletons. No interpretó pureza alta de clusters unitarios como éxito. El ganador final de clasificación no depende de HDBSCAN.

### Metric learning

El [tutorial y survey de metric learning](https://arxiv.org/abs/2201.09267) cubre redes siamesas, triplet loss, muestreo y minería. [PyTorch Metric Learning](https://kevinmusgrave.github.io/pytorch-metric-learning/losses/) ofrece pérdidas contrastivas, TripletMargin, MultiSimilarity, SupCon y mineros de pares.

El corpus actual no ofrece positivos y negativos juzgados por técnicos. Las carpetas mezclan sillas con mesas y archivadores con mostradores. Entrenar con esas etiquetas puede reforzar el ruido editorial y producir separación aparente. Antes de fine-tuning conviene reunir:

- pares graduados por similitud visual, constructiva y de coste como objetivos distintos;
- negativos difíciles del mismo tipo con diferencias de materiales, espesor o fabricación;
- separación por proyecto, fabricante o familia para impedir variantes cercanas entre train y test;
- un conjunto externo que no participe en minería, selección ni early stopping.

Con esos datos, una primera prueba razonable congelaría EG2 y entrenaría una cabeza pequeña o un adaptador con MultiSimilarity o triplet loss. Debe compararse contra kNN sobre el embedding congelado y contra el reranking determinista de componentes.

## Evidencia ejecutada

### Máquina y entorno

| Recurso | Valor observado |
|---|---|
| CPU | AMD Ryzen 9 9955HX, 16 núcleos y 32 hilos |
| RAM | 33.483.378.688 bytes instalados, 31,2 GiB visibles |
| GPU | NVIDIA GeForce RTX 5070 Ti Laptop |
| VRAM | 12.227 MiB |
| Driver | 591.86 |
| PyTorch | 2.10.0+cu128 |
| CUDA disponible | Sí |
| BF16 | Sí |
| Entorno | Python 3.14 aislado en `D:/Vexplorer-semantic-lab/venv` |

La unidad C: tenía cerca de 4 GB libres. El laboratorio situó entorno, caché, corpus y resultados en D: para evitar duplicar pesos y agotar C:.

### Artefactos

Cada NPZ conserva `ids` y `embeddings`. El JSON adjunto registra revisión, modo, precisión, dimensiones, hash del manifiesto, hashes ordenados de entradas, configuración, tiempo y hash del NPZ. El runner rechazó NaN, infinitos, dimensiones incorrectas, filas ausentes, duplicados y vectores cero. Los adaptadores recibieron bytes de imagen, texto neutral o ambos; no recibieron etiqueta, ruta, filename ni grupo.

| Representación | Revisión | Forma | Tiempo de encoding |
|---|---|---:|---:|
| DINOv3 imagen | `114c13799502…` | 117 × 384 | 0,492 s |
| MiniLM texto | `e8f8c211226b…` | 117 × 384 | 0,299 s |
| EG2 texto 768 | `f9972ac22e69…` | 117 × 768 | 0,570 s |
| EG2 imagen 768 | `f9972ac22e69…` | 117 × 768 | 14,053 s |
| EG2 mixto 768 | `f9972ac22e69…` | 117 × 768 | 17,815 s |
| EG2 texto 256 | `f9972ac22e69…` | 117 × 256 | 0,628 s |
| EG2 imagen 256 | `f9972ac22e69…` | 117 × 256 | 15,637 s |
| EG2 mixto 256 | `f9972ac22e69…` | 117 × 256 | 17,749 s |

Los tiempos excluyen descarga y carga. Miden un lote pequeño en esta máquina y no representan latencia de un servicio.

### Resultado local

Validation eligió EG2 mixto 768d, kNN con cinco vecinos y sin PCA. Sobre los 18 casos reservados obtuvo:

- macro-F1 0,826128;
- balanced accuracy 0,833333;
- Precision@5 0,888889;
- Hit@5 0,944444;
- exactitud 16/18.

La variante mixta 768 alcanzó macro-F1 1,0 y Precision@5 0,965 en los 17 casos de validation. Se probaron 228 configuraciones sobre ese conjunto pequeño, por lo que ese 1,0 refleja también riesgo de sobreajuste de selección.

Los dos errores de test ayudan a interpretar el límite de la taxonomía. El proveedor etiquetó un archivador como `simple-tables`, mientras el modelo lo acercó a `buffets`; etiquetó una silla de oficina como `simple-tables`, mientras el modelo la acercó a `sofas`. Los vecinos resultaron visualmente plausibles. No se cambiaron etiquetas después de ver los resultados.

KMeans con k=5 produjo ARI 0,919736, NMI 0,889626 y pureza 0,944444 en test. Ese análisis volvió a ajustar KMeans sobre los 18 vectores con k congelado, por lo que es transductivo. No demuestra un agrupador inductivo estable.

Estos resultados hacen de EG2 mixto 768 el ganador del protocolo local. No prueban que sea el mejor modelo universal, el mejor encoder para dibujos CAD o el más adecuado para precio, fabricación o BOM.

## Límites que condicionan cualquier decisión

- Cuatro carpetas de proveedor funcionan como etiquetas proxy. Tres clases sólo tienen tres casos en test.
- Los grupos reducen variantes obvias, pero no garantizan separación por fabricante o diseño.
- El corpus procede de una fuente y contiene categorías heterogéneas.
- Los renders eliminan cotas y texto. Otro sistema que use title block u OCR resuelve una tarea distinta.
- La similitud por etiqueta no mide intercambiabilidad, proceso de fabricación ni coste.
- Ningún modelo aprendió de técnicos del dominio.
- El experimento no midió objetos desconocidos, PDFs escaneados, planos complejos, despieces productivos ni otra empresa.
- El adaptador DINOv3 busca el snapshot de pesos exclusivamente en `~/.cache/huggingface/hub`. El argumento `--cache-dir` conserva resultados, pero no redirige esos pesos.
- La CLI no permite fijar una revisión de DINOv3. El runner elige un snapshot local completo y registra la revisión usada; reproducir exige conservar o preparar ese mismo snapshot.

## Próximos experimentos con valor

1. Construir una evaluación externa con mobiliario propio y separación por proyecto o fabricante.
2. Pedir a técnicos pares graduados para tres objetivos separados: parecido visual, parecido constructivo y utilidad para presupuestar.
3. Mantener EG2 mixto como recuperador inicial y rerankear con el comparador determinista de componentes.
4. Comparar EG2 256d y 768d en ese conjunto externo antes de elegir almacenamiento.
5. Probar Qwen3-VL-Embedding-2B sólo si el conjunto externo justifica el coste adicional.
6. Reservar UMAP para inspección hasta demostrar mejora reproducible fuera de validation.
7. Entrenar metric learning después de disponer de pares limpios y negativos difíciles.

La siguiente decisión no consiste en descargar más backbones. Consiste en definir similitud útil con técnicos y medirla sobre proyectos que el modelo no haya visto durante selección.
