# Contrato mesa desde vistas montadas 0.5

Acuerdo explícito A/B del 14 de noviembre de 2026. B es el único escritor de los modelos Pydantic. Este documento fija el alcance antes de implementar; los modelos Pydantic serán la fuente ejecutable única.

## Entrada y límites

La entrada es un DXF 2D con vistas ortográficas del mueble montado. El cliente envía `input_kind=mounted_orthographic_views` y `table_profile=rectangular_table_v1`; no hay autodetección. Ejes: `FRONT=(width,height)`, `TOP=(width,depth)`, `SIDE=(depth,height)`.

El DXF no aporta BOM, vistas de piezas, roles, cantidades ni montaje 3D. El ledger conserva cotas, vistas, conflictos y procedencia. Filename, manifiesto, referencia privada y respuestas del fixture no entran en prompt, herramientas o reglas.

`geometry_only` siempre devuelve el ledger. Solo genera catálogo si el usuario seleccionó `proposal_mode=catalog_baseline`, marcado como tal y nunca como IA. `live` exige `proposal_mode=model_generated` y la herramienta cerrada `proponer_descomposicion`. No hay fallback silencioso.

## Ledger observacional

`DrawingExtraction.input_kind` añade `mounted_orthographic_views`. A implementa:

```text
analyze_mounted_table(extraction: DrawingExtraction) -> MountedTableAnalysis
```

`MountedTableAnalysis` contiene perfil, `ledger_revision`, medidas admitidas, warnings y estado. Cada `TableMeasure` tiene ID, semántica/eje, valor métrico nullable, estado `observed|unknown|conflict` y refs measurement/view/evidence/entity. Un conflicto nunca se resuelve silenciosamente. El ledger es inmutable entre revisiones.

## Programa acotado

`TableProgramProposal` contiene perfil/revisión/origen; hasta 24 bindings ordenados; exactamente dos specs de tipo (`tabletop` y `side_support` o `corner_support`); cobertura mediante `consumed_measurement_ids` + `unassigned_measurement_ids`; premisas y evidencia separadas.

`TableBinding.operation=copy|add|subtract`. Sus operandos solo son `measure:<id>` o `binding:<id>` anterior. `copy` tiene 1 operando, `add` al menos 2 y `subtract` al menos 2, con semántica primero menos suma del resto. Se rechazan constantes, floats, coordenadas, refs futuras, ciclos, bindings muertos, unidades incompatibles y resultados no finitos/no positivos.

Los componentes solo refieren bindings L/W/T. Cantidad y placement proceden del registry:

| Rol | quantity rule | placement rule |
|---|---|---|
| `tabletop` | `top_one@1` | `top_flush@1` |
| `side_support` | `two_side_supports@1` | `side_supports_flush@1` |
| `corner_support` | `four_corner_supports@1` | `corner_supports_flush@1` |

No se duplican specs para codificar cantidad. Las topologías excluyentes son tapa + 2 soportes laterales o tapa + 4 patas.

El servidor conserva propuesta raw, normaliza símbolos, calcula programa canónico y `program_hash` independiente de IDs arbitrarios/orden, y registra versiones de ledger/perfil/reglas. Los intentos inválidos se auditan sin argumentos crudos ni secretos.

## Evaluación y revisión

A implementa:

```text
evaluate_table_program(
    analysis: MountedTableAnalysis,
    program: TableProgramProposal,
    decisions: tuple[TableReviewDecision, ...] = (),
    confirmed_values: tuple[TableConfirmedValue, ...] = (),
) -> EvaluatedTableProgram
```

`EvaluatedTableProgram` conserva bindings/componentes efectivos, ocurrencias, placements, dimensiones generales, constraints, issues, dependencias, cobertura, registry versions y programa/hash canónicos. `conflict` domina; después `unknown`; cualquier dependencia `proposed` mantiene el resultado `proposed`. Una operación sobre `observed|confirmed` produce `calculated`, nunca `observed`.

`TableReviewDecision` solo acepta/rechaza `program|component|binding|premise` por ID exacto y lleva razón; no contiene números. `TableConfirmedValue` apunta a un slot predeclarado `measurement_slot|binding_input_slot`, con `target_id`, `value_mm>0`, razón y `source=human`; solo resuelve `unknown|conflict|proposed`, nunca modifica `observed|calculated` ni una dimensión final de componente. Aceptar topología no rellena valores y confirmar un valor no acepta topología.

Cada revisión recalcula desde ledger crudo + decisiones humanas y persiste solo la copia efectiva en esa revisión. `completed` exige programa/topología/premisas/componentes aceptados; L/W/T positivas; qty/constraints/placements pass; cobertura completa; y ningún blocker/conflicto/desconocido. En otro caso queda `needs_review`.

`Result` añade `input_semantics=mounted_orthographic_views`, `table_analysis`, `table_programs`, `selected_table_program_id` y `evaluated_table_program`. `ReviewRequest` añade `table_program_id`, `table_decisions` y `table_confirmed_values`, excluyentes con legacy/parts-only.

## Escena y planos derivados

A implementa:

```text
derive_table_drawing_plan(
    extraction: DrawingExtraction,
    analysis: MountedTableAnalysis,
    evaluated: EvaluatedTableProgram,
    *, result_revision: int,
) -> TableDrawingPlan

reconstruct_table_scene(
    extraction: DrawingExtraction,
    analysis: MountedTableAnalysis,
    result: Result,
) -> ReconstructionScene
```

`TableDrawingPlan` queda ligado a revisión, program hash, rule versions y mm. Contiene dimensiones generales, componentes/ocurrencias y hojas `general|component|cut_sheet` con primitivas servidor `line|rect|dimension|text`, dependencias y estado `ready|incomplete`. Un desconocido se muestra como `?`/warning, nunca como cota falsa. No certifica fabricación.

El apoyo de planos implementa exclusivamente:

```text
render_table_drawings(plan: TableDrawingPlan) -> TableDrawingExports
```

`TableDrawingExports` contiene SVG/DXF bytes reabribles y sin referencias externas, uno por hoja/formato. B persiste y expone `TableDrawingManifest`: `sheet_id`, `kind`, `title`, `component_id|null`, `page`, `result_revision`, `program_hash`, `status`, `warnings`, `formats` y URLs. El renderer no crea modelos/API ni recalcula dimensiones.

La escena solo contiene sólidos para ocurrencias completas con placement de regla aceptada. Conserva program hash/dependencias/estado humano; no inventa piezas, espesores ni posiciones.

## Coste

El apoyo de costes implementa exclusivamente:

```text
estimate_table_costs(
    evaluated: EvaluatedTableProgram,
    *, result_revision: int,
) -> TableCostEstimate
```

El catálogo sintético pequeño vive en `table_costs.py`; su versión se expone. El cálculo usa ocurrencias, no vistas o tipos duplicados. Cada concepto conserva refs component/occurrence, fórmula, cantidad, unidad `EUR/m2|EUR/m3|EUR/m|EUR/unit|EUR/h`, tarifa, importe y estado `resolved|unknown|not_applicable`. El fijo se aplica una vez; canteado solo con scope explícito; horas, operaciones y acabado ausentes siguen unknown.

Se exponen `known_subtotal_eur` y `total_state=partial|complete`; si falta un concepto requerido, `grand_total_eur=null`. Todo queda ligado a revisión/hash. El módulo no crea modelos/API.

## Semántica y biblioteca

Solo una revisión aceptada puede guardarse. La mesa usa `FurnitureDescriptorV3`/`furniture-v3`, separado de v1/v2 y sus embeddings. Incluye perfil/familia, topología, dimensiones generales, roles/cantidades y features canónicas de componentes con estados/desconocidos; excluye IDs, filename, coordenadas y evidence IDs. Caché/similitud/grupos exigen misma versión/modelo/dimensión. La similitud no decide BOM, coste o revisión.

## API aditiva

- `POST /api/v1/runs`: añade `input_kind`, `table_profile` y `proposal_mode=none|catalog_baseline|model_generated`; combinaciones incompatibles dan 422.
- `GET /api/v1/runs/{run_id}/table?result_revision=N`: análisis, programas, seleccionado y evaluación.
- `POST /api/v1/runs/{run_id}/reviews`: misma ruta/stale guard; admite revisión de mesa.
- `GET /api/v1/runs/{run_id}/scene?result_revision=N`: escena efectiva.
- `POST /api/v1/runs/{run_id}/table-drawings`: genera/persiste revisión exacta; `GET .../table-drawings?result_revision=N` solo lee manifiesto.
- `GET /api/v1/runs/{run_id}/table-drawings/{sheet_id}.{format}?result_revision=N&program_hash=...`: bytes SVG/DXF.
- `POST /api/v1/runs/{run_id}/table-costs`: calcula revisión exacta; `GET .../table-costs?result_revision=N` solo lee persistido.
- Export JSON incluye análisis/programa raw-normalizado/revisión y scene/drawings/cost/descriptor/procedencia disponibles.

Lecturas no llaman ocultamente al proveedor. Una revisión nueva invalida derivados actuales sin borrar historia. Legacy y parts-only no cambian.

## Propiedad

- A: análisis de vistas montadas, evaluación, plan geométrico y reconstrucción.
- B: modelos, API, repositorio/revisión, harness y semántica/similitud.
- Apoyo planos: `backend/app/salida/technical_drawings.py` y tests.
- Apoyo costes: `backend/app/estimacion/table_costs.py` y tests.
- C: frontend. D: fixtures y aceptación independiente.
