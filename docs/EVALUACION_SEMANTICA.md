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

> Cambio de definición v2 (2026-11-14): los F1 publicados por v1 eran
> selectivos cuando existían desconocidos: omitían esos elementos de `fn` y
> por tanto podían mostrar 1,0 con cobertura parcial. Los F1 v2 miden
> recuperación completa y cuentan toda referencia requerida no recuperada,
> aunque la predicción se abstenga. La calidad condicionada a campos cubiertos
> se publica aparte como `covered_only`. Los valores históricos v1 y v2 no son
> comparables directamente.

El evaluador normaliza mayúsculas, acentos y separadores. Los aliases de la referencia pueden mapear un nombre funcional aceptado al rol canónico. Cada rol de referencia aparece una vez; `quantity` expresa sus ocurrencias. Esta restricción evita emparejamientos por orden o por un ID oculto.

`component_roles` calcula precisión, recobrado y F1 sobre roles. `physical_occurrences` suma `min(predicción, referencia)` como verdaderos positivos y conserva excesos y omisiones. Una pieza requerida omitida permanece en el denominador. Una pieza opcional omitida no penaliza.

El F1 principal usa exclusivamente elementos requeridos. Una pieza o relación
opcional acertada se publica como `optional_tp` (o `optional_tp_units`) y no
infla el recobrado requerido; tampoco cuenta como falso positivo.

`assembly_relations` compara la tripleta completa. Acertar `supported_by` no acredita `fixed_to`. Una relación adicional que ninguna alternativa admite cuenta como falso positivo.

`construction_alternatives` compara cada alternativa propuesta con el conjunto privado de alternativas válidas. Una propuesta admitida suma un verdadero positivo, una construcción no admitida suma un falso positivo y una alternativa de referencia no recuperada queda en el recobrado. Los nombres de alternativa no se emparejan; el evaluador compara sus conjuntos de relaciones.

Cada `valid_alternatives` declara una construcción completa aceptable. El evaluador puntúa la predicción contra la base y contra cada alternativa, y elige con este orden fijo: F1 de roles, F1 de ocurrencias, F1 de relaciones y menor suma de falsos positivos y falsos negativos. El informe publica `matched_variant`. Este conjunto de aceptación solo puede contener soluciones que el diseñador del fixture declaró legítimas antes de congelar la inferencia.

`ambiguity` acepta valores documentados para un campo. Por ejemplo, `component:door.quantity` puede aceptar `[1, 2]` cuando la vista no resuelve una hoja oculta. El evaluador escoge el valor aceptable más cercano a la predicción. Los valores fuera de la lista conservan sus errores.

## Desconocidos

La predicción declara desconocidos con un `scope` y un motivo. Los scopes implementados son:

- `component_roles`;
- `component:<role>.quantity`;
- `assembly_relations`;
- `assembly_relation:<subject_role>:<object_role>` para una unión concreta cuyo predicado no puede resolverse.

Un desconocido no fabrica un acierto: reduce `coverage`, aumenta
`unknown_reference_roles`, `unknown_reference_units` o
`unknown_reference_relations`, y la referencia requerida no recuperada cuenta
como `fn` en la métrica principal. `covered_only` permite analizar la calidad
de los campos respondidos sin confundirla con recuperación completa. Una
omisión sin declaración de desconocido también cuenta como error, pero no como
abstención.

El agregado publica numerador y denominador de cobertura, y separa resultados
por `split`. Desarrollo y holdout pueden aparecer en un mismo archivo sellado,
pero nunca se presentan solo como un número combinado. También publica
`case_count` y `project_count`; no publica IDs privados de proyecto.
`complete_case_count` exige cero falsos positivos, falsos negativos y
desconocidos en roles, ocurrencias y relaciones requeridas.

Cada informe v2 incluye `evaluation_batch_sha256`, derivado de los pares
ordenados `scenario_id` / `input_sha256` / `split`. El comparador exige el
mismo hash, además de los mismos conteos, para impedir deltas entre cohortes
distintas que casualmente tengan el mismo tamaño.

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

El adaptador también convierte las dos fases de un benchmark pareado. Lee `configuration.json`, `baseline.json` y `final.json`; en la fase final usa `outcome.effective_proposal_outcome.proposal`. Un caso sin outcome permanece en ambos manifiestos con predicción vacía y desconocidos explícitos.

```powershell
python -m tools.evaluate_semantic `
  --paired-output .runtime/paired-run `
  --output .runtime/paired-semantic
```

El comando crea `baseline-semantic-predictions.json` y `final-semantic-predictions.json`. La ruta de salida debe ser nueva. La publicación usa creación exclusiva y no reemplaza un freeze anterior.

Sellar y puntuar cada fase después de congelar ambas predicciones:

```powershell
python -m tools.seal_semantic_reference `
  --private-reference <directorio-privado-evaluador> `
  --predictions <freeze>\baseline-semantic-predictions.json

python -m tools.seal_semantic_reference `
  --private-reference <directorio-privado-evaluador> `
  --predictions <freeze>\final-semantic-predictions.json

python -m tools.evaluate_semantic `
  --predictions <freeze>\baseline-semantic-predictions.json `
  --references <referencia-sellada-baseline> `
  --output <informes>\baseline-report-v2.json

python -m tools.evaluate_semantic `
  --predictions <freeze>\final-semantic-predictions.json `
  --references <referencia-sellada-final> `
  --output <informes>\final-report-v2.json
```

Comparar proposal y reviewed bajo la misma definición v2:

```powershell
python -m tools.evaluate_semantic `
  --baseline-report <informes>\baseline-report-v2.json `
  --final-report <informes>\final-report-v2.json `
  --output <informes>\proposal-vs-reviewed-v2.json
```

Para comparar código original y corregido se ejecuta el mismo comando con
informes de la misma fase (`proposal` contra `proposal`, y `reviewed` contra
`reviewed`). El comparador exige el mismo dataset, casos, proyectos, splits y
definición de métrica. No incluye la lista de casos ni contenido de referencia.

El corpus ampliado contiene 80 planos, no 80 diseños independientes: son 16
topologías con cinco perfiles de vista cada una. El reservado principal usa
seis topologías nuevas (30 planos). No se calculan intervalos de confianza
tratando las cinco variantes de una topología como observaciones independientes.
