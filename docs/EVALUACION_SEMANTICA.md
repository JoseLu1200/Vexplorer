# Evaluación semántica offline

## Alcance

El evaluador mide cuatro resultados distintos:

- función del componente, mediante `role`;
- ocurrencias físicas, mediante `quantity`;
- relaciones de montaje, mediante tripletas `subject_role` / `relation` / `object_role`;
- cobertura, para separar errores de respuestas desconocidas.

Las dimensiones no intervienen en el emparejamiento. Dos tableros del mismo tamaño con funciones distintas cuentan como componentes distintos. Los IDs internos del runtime y los IDs del oráculo tampoco intervienen.

Los fixtures generados por el proyecto usan `certification: design_known_synthetic`. Esa marca documenta que el diseño es conocido porque lo produjo el generador. No acredita revisión de un técnico ni validez industrial.

## Frontera pública y referencia privada

El ZIP público conserva las claves vigentes `id`, `file`, `format`, `unit`, `view_kind`, `instruction` y `sha256`. `id` se traduce a `scenario_id` en la predicción congelada. El ZIP no publica `split`, familia, proyecto, certificación, alternativas ni relaciones de referencia.

El proceso sigue este orden:

1. El runtime recibe solo el caso público.
2. El adaptador guarda la predicción en un archivo nuevo.
3. El responsable calcula el SHA-256 de los bytes exactos de ese archivo y lo registra como `dataset.predictions_sha256` en el manifiesto privado.
4. El evaluador abre la referencia privada y rechaza cualquier diferencia de hash.

El manifiesto privado también exige `frozen_before_evaluation: true`, `partition_policy: project_and_family` y `reference_visibility: evaluator_only`. Una familia, proyecto o hash de entrada no puede aparecer en dos particiones.

## Contrato v1

Predicción congelada:

```json
{
  "schema_version": "semantic-evaluation/v1",
  "dataset_id": "semantic-benchmark",
  "cases": [{
    "scenario_id": "opaque-01",
    "input_sha256": "<64 hex>",
    "prediction": {
      "components": [
        {"label": "Costado", "role": "side_panel", "quantity": 2}
      ],
      "assembly_relations": [
        {"subject_role": "shelf", "relation": "supported_by", "object_role": "side_panel"}
      ],
      "assembly_alternatives": [{
        "alternative_id": "fixed-option",
        "assembly_relations": [
          {"subject_role": "shelf", "relation": "fixed_to", "object_role": "side_panel"}
        ]
      }],
      "unknowns": []
    }
  }]
}
```

Referencia privada:

```json
{
  "schema_version": "semantic-evaluation/v1",
  "dataset": {
    "id": "semantic-benchmark",
    "predictions_sha256": "<64 hex>",
    "frozen_before_evaluation": true,
    "partition_policy": "project_and_family",
    "reference_visibility": "evaluator_only"
  },
  "cases": [{
    "scenario_id": "opaque-01",
    "split": "holdout",
    "family_id": "cabinet",
    "project_id": "cabinet-project-07",
    "input_sha256": "<64 hex>",
    "reference": {
      "certification": "design_known_synthetic",
      "components": [
        {"label": "Costados", "role": "side_panel", "quantity": 2, "required": true, "aliases": []}
      ],
      "assembly_relations": [],
      "valid_alternatives": [],
      "ambiguity": []
    }
  }]
}
```

El parser rechaza campos no declarados. La predicción no admite `oracle_id`, `split` ni metadatos privados.

## Emparejamiento y métricas

El evaluador normaliza mayúsculas, acentos y separadores. Los aliases de la referencia pueden mapear un nombre funcional aceptado al rol canónico. Cada rol de referencia aparece una vez; `quantity` expresa sus ocurrencias. Esta restricción evita emparejamientos por orden o por un ID oculto.

`component_roles` calcula precisión, recobrado y F1 sobre roles. `physical_occurrences` suma `min(predicción, referencia)` como verdaderos positivos y conserva excesos y omisiones. Una pieza requerida omitida permanece en el denominador. Una pieza opcional omitida no penaliza.

`assembly_relations` compara la tripleta completa. Acertar `supported_by` no acredita `fixed_to`. Una relación adicional que ninguna alternativa admite cuenta como falso positivo.

`construction_alternatives` compara cada alternativa propuesta con el conjunto privado de construcciones aceptables. Cuando la referencia declara alternativas, el conjunto incluye la construcción base y cada `valid_alternatives`: dos alternativas nativas que expresen base y variante pueden alcanzar recobrado completo. Una construcción no admitida suma un falso positivo. Los nombres de alternativa no se emparejan; el evaluador compara sus conjuntos de relaciones. Una abstención explícita reduce `coverage` y aumenta `unknown_reference_alternatives` sin crear falsos negativos.

Cada `valid_alternatives` declara una construcción completa aceptable. El evaluador puntúa la predicción contra la base y contra cada alternativa, y elige con este orden fijo: F1 de roles, F1 de ocurrencias, F1 de relaciones y menor suma de falsos positivos y falsos negativos. El informe publica `matched_variant`. Este conjunto de aceptación solo puede contener soluciones que el diseñador del fixture declaró legítimas antes de congelar la inferencia.

`ambiguity` acepta valores documentados para un campo. Por ejemplo, `component:door.quantity` puede aceptar `[1, 2]` cuando la vista no resuelve una hoja oculta. El evaluador escoge el valor aceptable más cercano a la predicción. Los valores fuera de la lista conservan sus errores.

## Desconocidos

La predicción declara desconocidos con un `scope` y un motivo. Los scopes implementados son:

- `component_roles`;
- `component:<role>.quantity`;
- `assembly_relations`;
- `assembly_relation:<subject_role>:<object_role>` para una unión concreta cuyo predicado no puede resolverse.

Un desconocido no suma falsos positivos ni falsos negativos en ese campo. Reduce `coverage` y aumenta `unknown_reference_roles`, `unknown_reference_units` o `unknown_reference_relations`. Una omisión sin declaración de desconocido sí cuenta como error.

Los resultados `GeneralFurniture` anteriores al contrato de montaje no aportan un grafo. El adaptador conserva sus relaciones como desconocidas. En resultados nuevos puntúa solo relaciones con estado `hypothesis`; `unknown` y `conflict` reducen cobertura. No deriva uniones desde cajas, dimensiones o la referencia privada.

El crítico actual revisa cantidades y dimensiones, pero no confirma roles ni relaciones. En la fase final el adaptador publica una cantidad numérica solo cuando `machine_field_reviews` acepta `component:<id>.quantity`. El informe marca cada caso como `semantic_claim_status: hypothesis_unreviewed`; una puntuación alta no equivale a revisión técnica.

## CLI

Congelar un resultado nativo antes de abrir la referencia:

```powershell
python -m tools.evaluate_semantic `
  --native-output .runtime/native-output.json `
  --scenario-id opaque-01 `
  --input-sha256 <sha256-del-plano> `
  --dataset-id semantic-benchmark `
  --output .runtime/semantic-predictions.json
```

Evaluar el archivo ya congelado:

```powershell
python -m tools.evaluate_semantic `
  --predictions .runtime/semantic-predictions.json `
  --references data/private/semantic-reference.json `
  --output .runtime/semantic-report.json
```

El informe contiene agregados y resultados por `scenario_id`. No copia componentes, geometría ni respuestas de la referencia privada.

El adaptador también convierte las dos fases de un benchmark pareado. Verifica los SHA de `configuration.json`, `baseline.json`, `final.json` y `failure.json` contra `frozen-manifest.json`, además de `case_id` e `input_sha256` dentro de cada wrapper. En la fase final usa `outcome.effective_proposal_outcome.proposal`. Solo acepta un outcome ausente cuando `frozen-manifest.json` registra el caso como `failed_before_baseline` o `failed_after_baseline`; ese caso permanece en el manifiesto de predicciones con desconocidos explícitos.

```powershell
python -m tools.evaluate_semantic `
  --paired-output .runtime/paired-run `
  --output .runtime/paired-semantic
```

El comando crea `baseline-semantic-predictions.json` y `final-semantic-predictions.json`. La ruta de salida debe ser nueva. La publicación usa creación exclusiva y no reemplaza un freeze anterior.

## Resultado reservado congelado 2026-11-14

La cohorte contiene **seis casos: tres diseños estructurales reservados con dos variantes de vista cada uno**. No son seis diseños independientes. Los diseños son sintéticos `design_known_synthetic`, no verdad humana ni muestra industrial. El runtime recibió solo los ZIP públicos; las predicciones se congelaron antes de sellar la referencia y no se ajustó el sistema después de observar los scores.

Evidencia de freeze:

- manifiesto nativo combinado SHA-256 `782750b45432a16ccf84d7bf8de0608a984c949609b5b6307cfaa7e7a7d118b1`;
- predicción baseline SHA-256 `489dc57bfa19ef8bcb3a10b589ad39d6c42e42ff1967b096e0a7e5c1bf2a1e01`;
- predicción final SHA-256 `bbf0d936b69def44a635599f496793ae8e523622140975440f6e87a9b4f0540c`;
- referencia sellada baseline SHA-256 `6eea890c546092e99a5d86bee44e651c9bf321b180183ea05f5e7308e7ffb284`;
- referencia sellada final SHA-256 `e30df71732bca6757f14674550327082c68040502ad103ef29e3446e4b6b3861`.

| Fase | Métrica | Precisión | Recobrado | F1 | Cobertura | Conteos |
|---|---|---:|---:|---:|---:|---|
| Baseline | roles | 0,4737 | 0,3462 | 0,4000 | 1,0000 | TP 9, FP 10, FN 17 |
| Final | roles | 0,4737 | 0,3462 | 0,4000 | 1,0000 | TP 9, FP 10, FN 17 |
| Baseline | ocurrencias | 0,5926 | 0,3902 | 0,4706 | 0,9762 | TP 16, FP 11, FN 25, desconocidas 1 |
| Final | ocurrencias | 0,6400 | 0,3902 | 0,4848 | 0,9762 | TP 16, FP 9, FN 25, desconocidas 1 |
| Baseline/final | montaje | n/a | 0,0000 | n/a | 0,8500 | TP 0, FP 0, FN 17, desconocidas 3 |
| Baseline/final | alternativas | n/a | 0,0000 | n/a | 1,0000 | TP 0, FP 0, FN 12 |

La fase final solo elimina dos falsos positivos de ocurrencias. No mejora roles ni recobrado, y no recupera ninguna relación o alternativa correcta. Estos son resultados pobres y acotados; no acreditan capacidad semántica general, montaje fiable, aptitud de fabricación ni ahorro humano.

Los informes están en `.runtime/poc-closure-benchmark/heldout-semantic-v1/baseline-evaluation-report.json` (SHA-256 `6c40da00687d5a79828a2aa15d6bb58d32af11ae658ea4b6baabf931ef82080c`) y `final-evaluation-report.json` (SHA-256 `5d523ac35be670d50ff5155ea3edb97f1168fe81f93d36f207fd0a86635bc474`). Es seguro leerlos para auditoría: contienen agregados, conteos y resultados por ID opaco, pero no copian componentes, geometría, roles de referencia ni respuestas privadas.
