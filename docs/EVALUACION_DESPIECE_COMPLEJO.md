# Evaluación ciega del despiece complejo

Este protocolo acredita, por caso, un mínimo del 90 % de cobertura y precisión de piezas físicas de corte, y un mínimo del 90 % de cobertura y precisión de cotas. No acredita fabricabilidad, material, acabado, mecanizados ni herrajes.

## Custodia y secuencia

1. El runtime recibe solo el DXF público. El capturador no acepta rutas de referencia.
2. Se ejecutan primero y sin exclusiones `plank-030` y `plank-016`, ambos de desarrollo.
3. Se conserva el estado terminal, incluidos fallos, junto con config, revisiones, BOM derivado y SHA-256 del DXF.
4. `freeze_prediction_bundle` congela el resultado y su SHA-256 antes de que el evaluador abra la referencia privada.
5. El evaluador exige coincidencia exacta de `case_id`, split y SHA-256 del DXF entre predicción y referencia.
6. El holdout sellado `plank-066` se abre una sola vez, solo después de congelar motor/configuración y superar la cohorte de desarrollo. No se permite ajustar y repetir sobre él.

La referencia privada vive fuera del worktree. No se copia a prompts, runtime, release, pruebas de producto ni implementadores. El holdout se seleccionó mecánicamente del split editorial `test`: primer caso de 17–19 piezas cuyo `family_hash` cae en la partición holdout. No se eligió por el resultado del modelo.

## Salida elegible

Un borrador recuperable no cuenta como entrega. Para ser elegible, el trabajo debe terminar `succeeded`, tener revisión persistida de máquina con `auto_review_status=accepted`, validación constructiva `valid`, revisiones coincidentes y BOM/construcción derivados. `reviewed_incomplete` es admisible cuando lo desconocido queda fuera del objetivo, por ejemplo material o acabado; no lo es si faltan aceptación de existencia, tipo, geometría, cantidad o cotas de una pieza de corte.

Se puntúa el BOM derivado efectivo, nunca el `draft`. Los campos rechazados, en conflicto o abstained no se rescatan desde el borrador.

## Métricas preregistradas

La unidad es la ocurrencia física: `quantity=4` produce cuatro candidatos. `panel` y `linear_member` cuentan como piezas de corte. Un `hardware` solo se excluye si tipo y existencia están aceptados por la revisión; en otro caso permanece como candidato falso y bloquea el aprobado. El número de herrajes respaldados se informa aparte; su precisión no puede medirse porque la referencia PlankAssembly no anota herrajes.

El emparejamiento es óptimo 1:1 (Hungarian), no greedy, e invariante al intercambio largo/ancho. Una pieza con una cota desconocida puede ser TP si sus dos cotas conocidas son compatibles; la cota ausente reduce cobertura. Con cero o una cota conocida no se identifica la pieza.

Tolerancias inclusivas, fijas y no configurables por CLI:

- largo: ±1,0 mm;
- ancho: ±1,0 mm;
- espesor: ±0,2 mm.

Por cada caso se exige simultáneamente:

- recall de ocurrencias de corte ≥ 0,90;
- precision de ocurrencias de corte ≥ 0,90;
- `reference_dimension_coverage = celdas correctas / (3 × ocurrencias GT) ≥ 0,90`;
- `predicted_dimension_precision = celdas correctas / todas las celdas numéricas predichas ≥ 0,90`;
- salida final elegible y cero auxiliares sin autoridad.

Se reportan además exactitud conjunta de las tres cotas, MAE por eje y `paired_known_accuracy`. Estas son diagnósticas y no sustituyen los denominadores anteriores. El resumen micro es informativo: cada caso, incluido el holdout, debe aprobar individualmente. Los fallos y timeouts cuentan; no hay cherry-picking.

## Cohortes y artefactos

- desarrollo público: `.runtime/complex-cutlist-eval/development-manifest.json`;
- holdout público sellado: `.runtime/complex-cutlist-eval/holdout-manifest.sealed.json`;
- referencia del holdout: directorio privado hermano `.complex-cutlist-evaluator-private/holdout-sealed-v2`;
- capturador sin GT: `tools/capture_complex_cutlist_live.py` o el runner ignorado `run_candidates.py`;
- scorer offline: `tools/evaluate_complex_cutlist.py`;
- métricas y custodia: `evaluation/complex_cutlist.py`.

La ejecución objetivo debe probar desde `/api/v1/config` un presupuesto de 600 s y registrar el modelo revisor publicado. El modelo proponente y el revisor deben permanecer congelados como GPT-6.1 Sol y GPT-6 Astra durante desarrollo y holdout.

## Baseline histórico

El baseline local anterior usó 300 s, no 600 s. Ambos trabajos terminaron `provider_request_timeout`; por tanto entrega final = 0/2 y cobertura efectiva = 0, aunque los dos borradores puedan restaurarse. Vive en `.runtime/complex-cutlist-eval/baseline-v0`. Es diagnóstico y no demuestra el comportamiento de la configuración publicada de 600 s.

La línea base V4 congelada con 600 s terminó 2/2 jobs, pero 0/2 casos superaron el gate:

- `plank-030`: 16/16 piezas de referencia emparejadas y cobertura de cotas 1,00. La revisión quedó `incomplete`, la validación constructiva `incomplete` y 12 ocurrencias declaradas como hardware no obtuvieron autoridad aceptada de tipo/existencia. Bajo el protocolo anti-relabel quedan como candidatos no respaldados: precision 16/28 = 0,571.
- `plank-016`: 8/14 piezas emparejadas, recall y cobertura de cotas 0,571. Ocho cotas tripletas predichas son correctas; una novena fila (`rail`) conserva cantidad desconocida. La revisión también quedó `incomplete`.

Resumen micro informativo: 24/30 referencias emparejadas, recall 0,80 y precision 24/36 = 0,667. Predicciones congeladas: SHA-256 `5278c2e5b9b8cc5de378a96b41fd9459a6be1ef8e8784d37a8a24b18019c6aec`. No se abrió el holdout porque desarrollo no aprobó.
