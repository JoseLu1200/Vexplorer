# Evaluación reproducible de similitud

## Alcance

`evaluation/similarity_regression.py` ejecuta una regresión offline con muebles sintéticos definidos dentro del propio módulo. No abre referencias privadas, corpus reservados ni respuestas de benchmarks existentes. Su objetivo es detectar defectos mecánicos del ranking y la agrupación, no estimar relevancia empresarial.

El evaluador llama directamente a los helpers reales de `backend.app.similarity.service` para comparación técnica, clave canónica, deduplicación, reranking semántico y grupos complete-link. Conserva además una instantánea explícita de la fórmula geométrica anterior para presentar un antes/después sobre exactamente los mismos registros.

Ejecución:

```powershell
python -m evaluation.similarity_regression
python -m evaluation.similarity_regression --output .runtime/similarity-regression.json
python -m pytest tests/test_similarity_regression.py -q
```

No requiere red, credenciales ni proveedor de embeddings.

## Fixtures propios

La procedencia publicada por el informe es `inline_synthetic_furniture_v1`. Incluye:

- estantería base de 900 × 300 × 1200 mm, tablero de 18 mm e interior de 864 mm;
- equivalente con roles reordenados e identificadores distintos;
- tres registros duplicados adicionales del diseño equivalente;
- negativo duro con geometría idéntica pero acero y pintura negra en vez de tablero melaminado blanco;
- control `family=unknown` dentro de `furniture-v2`;
- variante dimensional de 990 mm;
- variante de 36 mm cuyo interior pasa de 864 a 828 mm;
- dos mesas `furniture-v3` de iguales dimensiones y estructuras distintas (`side_support_table` y `corner_support_table`);
- cadena A–B–C donde A–B y B–C alcanzan 0,98 bajo la fórmula anterior, pero A–C no;
- comparación `furniture-v2` frente a `furniture-v3`, que debe excluirse por espacio incompatible.

`furniture-v2` solo ofrece `rectangular_shelving|unknown`; por eso el control `unknown` no se presenta como un benchmark real entre familias. La separación estantería/mesa se comprueba como abstención entre versiones, no mediante un score cruzado inventado. Las estructuras de mesa sí se comparan dentro de `furniture-v3`.

## Métricas observadas

Resultados observados el 2026-11-14 con el conjunto anterior:

| Comprobación | Instantánea anterior | Servicio técnico actual |
|---|---:|---:|
| Top-1 relevante | no | sí |
| Reciprocal rank | 0,333333 | 1,0 |
| Recall de diseños relevantes únicos @5 | 0,333333 | 1,0 |
| Fracción duplicada @5 | 0,4 | 0,0 |
| Registros / diseños / duplicados | 8 / 5 / 3 | 8 / 5 / 3, deduplicados antes del ranking |

La instantánea anterior asigna score 1,0 tanto al negativo de material/acabado como al control de familia desconocida. También asigna 0,925 al cambio 18→36 mm; esa fórmula no consume las dimensiones de `part_features`, por lo que el cambio interior 864→828 queda documentado pero no interviene en ese score. El comparador actual produce, para este fixture, 1,0 para el equivalente, 0,990909 para la variante dimensional, 0,967448 para la variante de grosor y 0,9 para cada negativo duro.

La equivalencia bajo orden e IDs tiene fingerprint crudo distinto, pero la misma `canonical_design_key`. La deduplicación elige un representante determinista y distingue `record_count` de `design_count`; esos conteos impiden que copias de un diseño ocupen todo el top-k.

## Agrupación no transitiva

Con umbral sintético 0,98, la fórmula geométrica preservada mide A–B = 0,981818, B–C = 0,981818 y A–C = 0,965289. La conectividad simple produciría el componente `{A,B,C}` aunque no sea clique. El servicio actual usa complete-link y devuelve únicamente un par cuyos miembros satisfacen todos los pares internos; deja fuera el tercero. Si varios pares empatan, la elección es determinista.

Ese umbral pertenece al fixture. No es un umbral recomendado para producción, ni convierte el grupo en equivalencia, identidad constructiva o intercambiabilidad.

## Frontera semántica simulada

El evaluador construye vectores bidimensionales deterministas, con metadatos `fixture-vector-space`, y no llama a ningún proveedor:

- equivalente: coseno 0,999;
- negativo duro: coseno 0,999546.

El orden por coseno bruto coloca primero al negativo. `rank_semantic_candidates` conserva el coseno como evidencia semántica pero ordena primero por `technical_score`, de modo que el equivalente queda delante. Esto ensaya la frontera, los metadatos compatibles y el reranking ante cosenos casi idénticos. No mide el ranking de `text-embedding-3-small`, no valida la calidad de ningún embedding real y no reproduce afirmaciones de auditorías previas como si fueran nuevas mediciones.

## Interpretación y límites

- Los juicios de relevancia son decisiones sintéticas declaradas en el fixture, no etiquetas de técnicos ni resultados de negocio.
- Material y acabado diferentes se tratan aquí como negativo duro para presionar el comparador; en un uso real su importancia depende de la consulta y del proceso de fabricación.
- Los scores no son probabilidades y no demuestran mismo coste, tiempo, mecanizado, montaje o intercambiabilidad.
- No se usan embeddings reales. El informe publica `uses_actual_embeddings=false`, `provider_called=false` y `actual_embedding_ranking_measured=false`.
- No se usan respuestas ocultas. El fixture publica `external_reference_paths=()` y `uses_hidden_benchmark_answers=false`.
- La evaluación comprueba invariantes y regresiones conocidas sobre una galería pequeña. No sustituye un benchmark independiente, estratificado por familias y proyectos, con anotación ciega de relevancia.
