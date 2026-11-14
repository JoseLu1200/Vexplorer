# Comparación local de clasificadores

## Protocolo vigente fijado antes de ejecutar

Fecha: 2026-11-14. Este protocolo sustituye, antes de ajustar modelos o calcular métricas, una primera interpretación que proponía kNN geométrico y CAD extra como OOD. Esa interpretación no se ejecutó ni se puntúa. La coordinación aclaró el control y los tres corpus.

La comparación es retrospectiva. El equipo ya abrió los tests de core y CAD extra en experimentos anteriores. Los resultados nuevos permiten comparar clasificadores con baselines existentes; no constituyen una evaluación ciega.

### Datos

- Core: 82 train, 17 validation y 18 test. Se ajusta en train, se selecciona en validation y se informa test como análisis post hoc.
- CAD extra: 262 train, 56 validation y 55 test. Se repite el mismo procedimiento con sus propias etiquetas y sin mezclar filas con core.
- Entrada supervisada: embedding EG2 mixed de 768 dimensiones y las mismas 27 características geométricas de cada manifiesto.
- Control: kNN usa solo EG2 mixed 768.
- Prueba forzada fuera de dominio: las 14 muestras del manifiesto engineering. El ganador core debe asignar una de las cuatro etiquetas core. Sus etiquetas de origen no miden acierto core.

El informe registrará SHA-256 de los tres manifiestos y NPZ, IDs engineering, dimensiones y distribuciones. Si faltan IDs, hay duplicados, cambian las 27 columnas o los embeddings no tienen 768 dimensiones, la corrida falla antes de ajustar.

### Candidatos

1. `knn_eg2_k5`: EG2 normalizado L2, distancia coseno, cinco vecinos y ponderación por distancia.
2. `logreg_combined`: EG2 normalizado L2 concatenado con geometría; `StandardScaler` del vector combinado y `LogisticRegression` balanceada. Se comparan `C=0.1`, `1` y `10`, con `max_iter=2000` y semilla 0.
3. `histgb_pca_geometry`: PCA de EG2 con 32 o 64 componentes, ajustado solo en train, concatenado con geometría estandarizada. `HistGradientBoostingClassifier` usa `max_iter=100`, `max_depth=3`, `l2_regularization=1`, `class_weight="balanced"` y semilla 0.

No se ejecuta CV adicional. Cada corpus conserva sus splits y grupos.

### Selección y resultados

El orden de selección es macro-F1, balanced accuracy y el orden de candidatos anterior. Las métricas de validation incluyen matriz de confusión, precisión, recall y F1 por clase, e IDs erróneos.

Tras elegir un candidato por corpus, el script evalúa su test existente y marca esas cifras como post hoc. Compara core con el baseline test macro-F1 0,8261278 y CAD extra con 0,778, sin tratarlos como umbrales fijados antes de test.

El ganador core clasifica las 14 muestras engineering. El informe publica asignaciones forzadas, confianza máxima cuando el modelo la ofrece y similitud al vecino más cercano para el control. No ajusta un umbral OOD. `route_to_review` queda como opción de producto sin eficacia medida.

Jev 1.14 es una referencia externa de API, no un checkpoint local. La comparación local mide clasificadores cerrados sobre descriptores ya extraídos; no mide interpretación CAD de extremo a extremo.

## Resultados observados

La corrida usó los hashes registrados en `docs/experiments/classifier-comparison-2026-11-14/local-summary.json`. El informe completo y los clasificadores quedan en `D:/Vexplorer-semantic-lab/classifier-comparison/local/`.

Los `.joblib` contienen sólo modelos ajustados por este script y componentes de scikit-learn. Joblib usa pickle: carga únicamente estos artefactos propios cuyos hashes y procedencia controles; no cargues archivos externos o recibidos.

| Corpus | Ganador por validation | Validation macro-F1 / BA | Test post hoc macro-F1 / BA | Baseline test macro-F1 |
|---|---|---:|---:|---:|
| Core | kNN EG2, k=5 | 1,0000 / 1,0000 | 0,8261 / 0,8333 | 0,8261 |
| CAD extra | Regresión logística EG2+geometría, C=0,1 | 0,8838 / 0,8956 | 0,8445 / 0,8604 | 0,7780 |

El clasificador supervisado no mejoró el control kNN en core. En CAD extra, la selección por validation eligió regresión logística y su test post hoc superó el baseline por 0,0665 macro-F1. Esa diferencia es descriptiva porque el equipo conocía el test antes de esta comparación.

El kNN core asignó las 14 muestras engineering a `buffets` (11), `sofas` (2) y `simple-tables` (1). La concentración en `buffets` muestra el comportamiento cerrado bajo cambio de dominio; no mide corrección ni justifica un umbral automático. Una integración operativa debe enviar estos casos a revisión hasta disponer de una evaluación OOD independiente.
