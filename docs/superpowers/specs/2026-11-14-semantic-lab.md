# Laboratorio de recuperación y clasificación de mobiliario

## Objetivo y autorización
Experimento solicitado explícitamente por el usuario: probar vías distintas con agentes GPT-6.1 Sol y revisión final GPT-6 Astra. Entregar código reproducible, resultados observados y una elección justificada. Es investigación local aislada; no se modifica ni despliega el producto actual.

## Vías
1. Descriptores geométricos deterministas desde DXF, normalizados, con medidas de cobertura.
2. Texto construido exclusivamente desde observaciones extraídas; TF-IDF como control y embedding aprendido cuando disponible.
3. Imágenes renderizadas del plano sin títulos/rutas/etiquetas; modelos visuales o multimodales locales, priorizando EmbeddingGemma.
4. Fusión y reducción PCA; clasificación sencilla y agrupación sin etiquetas. Se comparan contra vecinos por geometría y prevalencia.

## Evidencia admisible
- Corpus real local; categorías de carpetas son proxy de evaluación y nunca entrada de features/modelos.
- Separación por hashes/grupos antes de ajustar transformaciones; ningún ajuste de hiperparámetros sobre test.
- Distinción entre retrieval de tipo visual, clasificación de categoría, composición constructiva y coste.
- La fuente CAD y derivados permanecen fuera de Git, igual que los pesos.
- No se inventan medidas, embeddings, resultados ni disponibilidad de modelos. Fallos se registran como fallos.
- Preparación sintética propia puede probar invariancias y sensibilidad, pero no acredita generalización real.

## Interfaz experimental
Manifiesto JSON con `schema_version: 1`, `metadata` y `samples`.
Cada sample: `id`, `source_path`, `image_path`, `label`, `label_source`, `group_id`, `split` (train/validation/test), `features` (mapa numérico finito), `text` (descriptor sin categoría, nombre de archivo ni texto libre del plano).
`label`, `source_path`, `group_id` y rutas no pueden alimentar embeddings ni features. `image_path` sólo localiza bytes del render.
Embeddings aprendidos: NPZ con `ids` y matriz `embeddings`, y JSON de procedencia/configuración/timing. IDs no son features.

## Evaluación
Recall/precision de vecinos por categoría proxy, macro-F1/balanced accuracy de clasificación y ARI/NMI/pureza/cobertura de clusters. Reportar siempre número de clases, tamaños, distribución y métricas de baselines. PCA y escalado ajustados sólo en train; selección en validation; test se abre una vez fijado método/configuración. Gráficas no prueban éxito.

## Entrega
CLI local para preparar/evaluar/consultar, pruebas significativas de ausencia de leakage y métricas, informe con limitaciones y revisión final independiente. No prometer costes industriales ni clasificación general basándose en un corpus pequeño.
