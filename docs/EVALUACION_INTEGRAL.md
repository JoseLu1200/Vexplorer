# Evaluación integral offline

Este evaluador compara una salida ya congelada con una referencia que solo abre el proceso de evaluación. No forma parte del backend, no tiene endpoint y no debe importarse desde el runtime, el proveedor, los prompts, las herramientas ni el índice histórico. El informe contiene exclusivamente agregados; no copia rutas, componentes ni contenido del oráculo.

Los fixtures propios prueban el cálculo y el aislamiento del evaluador. Se etiquetan `developer_fixture` y no constituyen un benchmark ciego ni evidencia de utilidad empresarial. `independent_review` identifica una referencia revisada independiente, y `observed_technician_study` sesiones observadas; ninguna etiqueta convierte por sí sola una diferencia temporal en ahorro causal.

## Entradas separadas

El fichero de predicciones se produce y congela antes de abrir la referencia privada:

```json
{
  "schema_version": "1.0",
  "dataset_id": "pilot-2026-11",
  "cases": [{
    "id": "case-001",
    "components": [{
      "key": "prediction-local-1",
      "quantity": null,
      "dimensions_mm": {"length": 600, "width": 400, "thickness": null}
    }],
    "retrieved_item_ids": null,
    "cost": null,
    "hours": null,
    "assisted": null
  }]
}
```

La referencia vive fuera de las rutas accesibles al producto. Declara proyecto, familia, grupo de duplicados y split para impedir que revisiones, escalados o derivados crucen particiones. `component_matches` es una alineación realizada por el evaluador después de congelar la salida: evita dar al sistema las claves ocultas del oráculo.

```json
{
  "schema_version": "1.0",
  "dataset": {
    "id": "pilot-2026-11",
    "evidence_kind": "independent_review",
    "frozen_before_evaluation": true,
    "predictions_sha256": "<sha256 de los bytes exactos del fichero congelado>",
    "partition_policy": "project_and_family",
    "component_matching": "reference_alignment",
    "retrieval_items": {
      "historic-42": {
        "project_id": "old-project",
        "family_id": "other-family",
        "duplicate_group_id": "old-revision-group"
      }
    }
  },
  "cases": [{
    "id": "case-001",
    "split": "test",
    "project_id": "new-project",
    "family_id": "cabinet-family",
    "duplicate_group_id": "new-revision-group",
    "components": [{
      "key": "oracle-private-7",
      "quantity": 2,
      "dimensions_mm": {"length": 600, "width": 400, "thickness": 18}
    }],
    "component_matches": [{
      "prediction_key": "prediction-local-1",
      "reference_key": "oracle-private-7"
    }],
    "relevant_item_ids": ["historic-42"],
    "cost": null,
    "hours": null,
    "technician_baseline": null
  }]
}
```

Cantidad, dimensiones, coste, horas y tiempos admiten abstención mediante `null` donde se muestra. Una cantidad desconocida no se convierte en uno: reduce cobertura. Las dimensiones deben ser positivas cuando existen; importes y horas no pueden ser negativos. El hash enlaza la referencia con los bytes exactos de la predicción, pero no prueba por sí mismo cronología ni independencia del proceso.

Cuando existen, el coste usa `{value,currency,scope_id,effective_date}` y las horas `{value,scope_id}`. Solo se puntúan si moneda, alcance y fecha económica coinciden exactamente (y el alcance en horas); las incompatibilidades reducen cobertura y se cuentan por motivo. `technician_baseline` y `assisted` exigen `duration_seconds`, `acceptable` y el entero no negativo `corrections_until_acceptable`.

La preservación de ambigüedad usa `scenarios:[{key}]` en la predicción y `acceptable_scenarios` más `scenario_matches` privados en la referencia. Las claves locales no revelan IDs del oráculo. Los componentes predichos sin alineación se cuentan como hipótesis no respaldadas; campos corregidos por una persona permanecen `not measured` hasta disponer de disposiciones estructuradas.

La revisión automática es una propiedad de proceso ortogonal a la certeza. `quantity_state`, `dimension_states` y el estado de escenario siguen siendo `hypothesis|observed|derived|confirmed|unknown|conflict`. `quantity_review_status`, `dimension_review_statuses` y `scenario.review_status` usan `unreviewed|auto_reviewed|human_reviewed`. Un crítico automático nunca convierte una hipótesis en confirmación. El informe separa `by_prediction_state` de `by_review_status`, incluida exactitud provisional de cantidades y recobrado de ocurrencias.

## Ejecución

### Congelación pareada pública

`tools.run_general_benchmark` ejecuta el flujo nativo de mobiliario general sin abrir referencias ni puntuar resultados. El runner escribe `baseline.json` con creación exclusiva antes de invocar al crítico; un fallo posterior conserva esa primera pasada y su SHA-256. Al terminar la cohorte convierte determinísticamente los objetos nativos en `baseline-predictions.json` y `final-predictions.json`, ambos con `schema_version: 1.0`, y los incluye en `frozen-manifest.json`. En el manifest final evaluable solo conserva el valor numérico de un campo cuando la decisión de campo del crítico es `accepted`; valores rechazados, conflictivos, abstenciones o campos no revisados pasan a `null/unknown`, sin modificar el outcome ni la traza raw. Un escenario provisional se conserva con revisión global `accepted|incomplete` y se omite en `conflict|abstained`. Un caso fallido permanece en ambos manifiestos con componentes vacíos, de modo que la evaluación posterior contabilice el fallo en el denominador. Solo después de congelar ambos ficheros puede abrirse la referencia privada para construir sus alineaciones; baseline y final requieren copias de referencia separadas, cada una enlazada al SHA-256 exacto de su propio fichero de predicciones.

Para blind20 el proceso de inferencia debe recibir exclusivamente los ZIP públicos individuales de `agent_cases`; no debe recibir el directorio raíz del adaptador, su `cases.json` ni el directorio privado:

```powershell
.venv\Scripts\python.exe -m tools.run_general_benchmark `
  --input ..\plankassembly_adapter_blind20_v2\agent_cases `
  --output .runtime\transcript-qa\blind20-paired `
  --dataset-id plankassembly-blind20-v2 `
  --strict-bundles `
  --workers 2
```

Los valores por defecto son proponente `gpt-6.1-sol`, crítico `gpt-6-astra`, 16.384 tokens máximos, cinco llamadas de revisión, dos reparaciones de validación, dos workers y 300 segundos por caso. Modelos y presupuestos son configurables dentro de los límites del backend. La clave se carga desde `.env` mediante la configuración del servidor: no existe argumento CLI para ella y no se escribe en trazas ni manifiestos. Las trazas guardan respuestas estructuradas de herramientas y errores acotados, no prompts, cuerpos HTTP ni razonamiento oculto.

En modo estricto cada ZIP debe contener exactamente `input.dxf` y `case.json`. Nombres, ID opaco, metadatos, tamaños declarados/comprimidos, ratio de compresión y SHA-256 se validan antes de descomprimir el DXF; no se extraen rutas ni se ejecuta contenido del bundle. Configuración, fuentes, PNG, código del runner/backend y dependencias declaradas quedan enlazados por SHA-256. El log y los timestamps locales documentan el orden operativo, pero no son una prueba criptográfica de cronología. Las pruebas offline no hacen llamadas a proveedores.

```powershell
python -m tools.evaluate_cases `
  --predictions .runtime/evaluation/frozen-predictions.json `
  --references D:\private\references.json `
  --output .runtime/evaluation/report.json `
  --tolerance-mm 1 `
  --retrieval-k 5
```

El comando falla si el hash no coincide, los IDs de dataset/casos no coinciden, proyecto o familia cruza splits, la alineación no es uno-a-uno o un comparable carece de metadatos privados para comprobar fugas. Un comparable del mismo proyecto, familia o grupo de duplicados se excluye del ranking puntuado y se cuenta como fuga. La salida no puede ser la misma ruta resuelta que ninguna entrada y se publica mediante reemplazo atómico.

## Métricas y límites

- BOM: precisión/recobrado/F1 por tipos y por cantidades. La cantidad publica además cobertura de componentes con verdad conocida y predicción conocida.
- Dimensiones: MAE, tasa dentro de la tolerancia y cobertura sobre campos de referencia conocidos. Solo se comparan componentes alineados.
- Recuperación: macro Precision@k y Recall@k sobre casos con relevancia anotada, cobertura y candidatos fugados. El ranking limpio excluye mismo proyecto, familia o derivado.
- Coste y horas: MAE, cobertura y MAPE solo cuando la referencia es distinta de cero y sus metadatos son compatibles. Un desconocido o alcance incompatible no se imputa como acierto ni como cero.
- Ambigüedad e hipótesis: recobrado de escenarios aceptables, escenarios predichos no respaldados y componentes predichos sin alineación.
- Tiempo y correcciones: medias de baseline, asistencia y diferencias observadas solo para pares aceptables. El campo `savings_claim_supported` permanece `false`: el informe describe observaciones, no ahorro causal, productividad de 50 personas ni retorno económico.

Para sostener valor empresarial faltan casos representativos congelados antes del ensayo, juicios de relevancia de técnicos, costes y horas reales con alcance compatible, y sesiones pareadas con protocolo y criterio de ficha aceptable. Deben informarse denominadores, abstenciones y correcciones; no se extrapola desde muestras pequeñas.

## Estado del ensayo PlankAssembly local

El adaptador local `plankassembly_adapter_trial_v1` contiene seis entradas externas preparadas y referencia separada, pero su propio manifiesto declara `inference_evaluated: false`; cinco casos son `development` y solo uno `holdout`. No existe un fichero de predicciones congeladas compatible. Por ello es material diagnóstico de adaptación, no un resultado de inferencia ni un benchmark ciego. No se copian ni redistribuyen sus datos desde este repositorio.

Después se ejecutó una pasada live real `v4` con `gpt-6.1-sol` sobre los seis DXF públicos y se congelaron sus seis respuestas con SHA-256 antes de puntuarlas. El evaluador agrupó componentes de referencia por dimensiones físicas y alineó uno-a-uno únicamente tripletas dentro de 1 mm. Resultado agregado diagnóstico: 38 tipos propuestos frente a 36 tipos de referencia agrupados, 33 alineados (precisión 0,868; recobrado 0,917; F1 0,892); cinco hipótesis de componente quedaron sin respaldo. Se compararon 99 de 108 campos dimensionales (cobertura 0,917), todos con estado `hypothesis`: MAE 0,202 mm y 97/99 dentro de 1 mm. Es una métrica de tipos de panel alineados por dimensiones, no un juicio independiente de corrección semántica de la BOM. Agrupar piezas iguales y elegir la alineación geométrica admisible puede elevar el resultado frente a una comparación exacta por ocurrencia. Estas cifras muestran coincidencia geométrica en la muestra preparada; no confirman identidad semántica, montaje ni aptitud industrial.

Todas las cantidades permanecieron desconocidas: cobertura de cantidad 0/36 y recobrado de ocurrencias 0/54. Las seis propuestas conservaron un escenario local, pero no hubo alineación evaluadora suficiente para afirmar que preservaran la construcción aceptable (0/6); se cuentan como escenarios no respaldados, no como falsedad demostrada. Coste, horas, recuperación histórica, tiempos y correcciones no tenían referencia/predicción compatible y quedan con denominador cero. No se afirma ahorro ni cumplimiento completo del objetivo de la transcripción. Artefactos agregados locales: `.runtime/transcript-qa/plank-v4-evaluation/report.json`; las referencias privadas no se versionan ni se sirven.

Una segunda pasada preseleccionada antes de inferencia usó diez modelos distintos del split oficial `test` (nueve marcados development y un holdout por el adaptador). Las diez ejecuciones live se congelaron antes de abrir referencias. Agregado: 88 tipos propuestos, 77 tipos dimensionales de referencia y 77 alineados (P=0,875, R=1,000, F1=0,933); 11 hipótesis no alineadas. Los 231 campos comparados eran hipótesis, con MAE 0,719 mm y 229 dentro de 1 mm. Cantidades: cobertura 0/77 y recobrado 0/96 ocurrencias. Escenarios respaldados: 0/10. El único holdout no sostiene una afirmación de generalización, y las cohortes son estructurales, no tres familias semánticas de muebles. Costes, horas, comparables y tiempos permanecen sin evaluar.
