# Contrato mesa desde vistas montadas 0.5

Acuerdo explícito A/B del 14 de noviembre de 2026. B es el único escritor de los modelos Pydantic. Este documento fija el alcance antes de implementar; los modelos Pydantic serán la fuente ejecutable única.

## Entrada y límites

La entrada es un DXF 2D con vistas ortográficas del mueble montado. El cliente envía `input_kind=mounted_orthographic_views` y `table_profile=rectangular_table_v1`; no hay autodetección. Ejes: `FRONT=(width,height)`, `TOP=(width,depth)`, `SIDE=(depth,height)`.

El DXF no aporta BOM, vistas de piezas, roles, cantidades ni montaje 3D. El ledger conserva cotas, vistas, conflictos y procedencia. Filename, manifiesto, referencia privada y respuestas del fixture no entran en prompt, herramientas o reglas.

`geometry_only` siempre devuelve el ledger. Solo genera catálogo si el usuario seleccionó `proposal_mode=catalog_baseline` y `table_template_id=side_supports_v1|corner_supports_v1`, marcado como tal y nunca como IA. `live` exige `proposal_mode=model_generated` y la herramienta cerrada `proponer_descomposicion`. No hay fallback silencioso ni selección de topología por apariencia.

## Ledger observacional

`DrawingExtraction.input_kind` añade `mounted_orthographic_views`. A implementa:

```text
analyze_mounted_table(extraction: DrawingExtraction) -> MountedTableAnalysis
```

`MountedTableAnalysis` contiene perfil, `ledger_revision`, medidas admitidas, warnings y estado. Cada `TableMeasure` tiene ID, semántica/eje, valor métrico nullable, estado `observed|unknown|conflict`, relación geométrica tipada y refs measurement/view/evidence/entity. `envelope_extent` identifica una extensión geométrica sin fingir cota; offsets conservan su borde/eje. El análisis crea además slots `unknown` definidos por perfil cuando falta sección/espesor; se distinguen de una medida CAD observada y no inventan evidencia. Un conflicto nunca se resuelve silenciosamente. El ledger es inmutable entre revisiones.

## Programa acotado

`TableProgramProposal` contiene perfil/revisión/origen; hasta 24 bindings ordenados; exactamente dos specs de tipo (`tabletop` y `side_support` o `corner_support`); premisas estructuradas y evidencia separadas. El modelo no declara una cobertura confiable: el evaluador deriva los IDs consumidos desde operand refs y crea `TableMeasurementDisposition{measurement_id,reason,blocking}` para el resto. Conflictos son siempre bloqueantes; una cota redundante puede ser no bloqueante. `completed` solo admite disposiciones no bloqueantes.

`TableBinding.operation=copy|add|subtract`. Sus operandos solo son `measure:<id>` o `binding:<id>` anterior. `copy` tiene 1 operando, `add` al menos 2 y `subtract` al menos 2, con semántica primero menos suma del resto. Se rechazan constantes, floats, coordenadas, refs futuras, ciclos, bindings muertos, unidades incompatibles y resultados no finitos/no positivos.

Los componentes solo refieren bindings L/W/T. Cantidad y placement proceden del registry:

| Rol | quantity rule | placement rule |
|---|---|---|
| `tabletop` | `top_one@1` | `top_flush@1` |
| `side_support` | `two_side_supports@1` | `side_supports_flush@1` |
| `corner_support` | `four_corner_supports@1` | `corner_supports_flush@1` |

No se duplican specs para codificar cantidad. Las topologías excluyentes son tapa + 2 soportes laterales o tapa + 4 patas.

El servidor conserva propuesta raw y calcula forma/hash canónicos topológicamente: asigna IDs canónicos; puede ordenar specs/componentes; ordena operandos de `add`; en `subtract` preserva el minuendo y solo ordena los sustraendos. La identidad incluye ledger, perfil y versiones de reglas. Los intentos inválidos se auditan sin argumentos crudos ni secretos.

Para la selección humana explícita de baseline, A implementa también:

```text
catalog_table_programs(
    analysis: MountedTableAnalysis,
) -> tuple[TableProgramProposal, ...]
```

Devuelve las dos alternativas incompatibles side/corner con `proposal_origin=catalog_baseline`; B conserva únicamente la que coincide con el `table_template_id` solicitado. Ninguna se selecciona por apariencia. Secciones o espesores ausentes son `TableMeasure unknown` del perfil, no mediciones CAD fantasma. B no duplica estas reglas en repositorio.

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

`EvaluatedTableProgram` conserva bindings/componentes efectivos, ocurrencias, placements, dimensiones generales, constraints, issues, dependencias, cobertura, registry versions y programa/hash canónicos. `conflict` domina; después `unknown`. Antes de revisión, todo binding/componente/placement creado por programa permanece `proposed` aunque copie una medida observed. Aceptar el programa valida topología/bindings y permite que una operación sobre `observed|confirmed` pase a `calculated`, nunca `observed`; no acepta componentes ni premisas.

`TablePremise` tiene ID, kind cerrado, `required=true` fijado por registry y descripción; el texto libre nunca participa en completitud. `profile`, `ledger_revision`, `proposal_origin` y required los inyecta/valida servidor y no son autoridad del tool. `TableReviewDecision` solo acepta/rechaza `program|component|premise` por ID exacto y lleva razón; no contiene números. Las decisiones son únicas por target; reject bloquea dependientes; aceptar programa no acepta componentes/premisas. `TableConfirmedValue` solo apunta a `target_kind=measurement_slot`, con `target_id`, `value_mm>0`, razón y `source=human`; resuelve un overlay `unknown|conflict|proposed`, nunca modifica `TableMeasure observed|calculated` ni una dimensión final. Aceptar topología no rellena valores y confirmar un valor no acepta topología.

Cada revisión recalcula desde ledger crudo + decisiones humanas y persiste solo la copia efectiva en esa revisión. `completed` exige registry/versiones vigentes, decisiones no contradictorias, programa/topología, cada premisa required y cada componente aceptados; L/W/T positivas; qty/constraints/placements pass; y ninguna disposición bloqueante/conflicto/desconocido. En otro caso queda `needs_review`.

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

## Visión opcional acotada

La visión live es una ayuda contextual exclusiva de `mounted_orthographic_views`; no se expone en legacy ni parts-only. Está desactivada por defecto y solo se habilita con configuración explícita del servidor. Con el modo apagado se conserva el prompt de evidencia vectorial sin imágenes y no se anuncia ninguna herramienta visual.

Con el modo activo, el esquema Pydantic `VisualizeTableViewArgs{view_id}` respalda la herramienta nativa `visualizar_vista`. El modelo debe solicitar una vista anunciada por ID; el servidor responde por el mismo `call_id` con SHA-256, dimensiones y marcas `Mnnn -> contour|entity ID`, y aporta un PNG Set-of-Mark en el siguiente input. No se preenvían imágenes. Hay un máximo de 3 intentos visuales por ejecución, incluidos duplicados y errores.

El renderer consume únicamente el `DrawingExtraction` ya autorizado: no abre el DXF, paths, URLs, sidecars ni referencias privadas. Excluye `TEXT|MTEXT|ATTRIB|DIMENSION` de la geometría visual; representa `CIRCLE|ARC` desde `CircularGeometry` y nunca como chords de `points_mm`. Los límites previos a raster son 100 contornos, 500 entidades, 20.000 puntos teselados, lado máximo 1024 px y PNG máximo 2.000.000 bytes por vista. Los errores son explícitos (`unknown_view`, `vision_budget_exceeded`, `vision_geometry_unavailable`).

La imagen no es fuente de medidas: cualquier número, cantidad, binding o componente debe seguir respaldado por medidas y referencias vectoriales del ledger. Las trazas solo conservan tool name, view ID, SHA y número de marcas; nunca bytes, base64, prompt o argumentos crudos.

Acuerdo explícito A/B 2026-11-14: A y B aceptan `VisualizeTableViewArgs`, el gate mesa-only opt-in, el renderer exclusivo desde ledger/`CircularGeometry`, los presupuestos anteriores y la obligación de visualizar al menos una vista antes de proponer cuando el modo está ON. No cambia las firmas geométricas de A.

## Coste

El apoyo de costes implementa exclusivamente:

```text
estimate_table_costs(
    evaluated: EvaluatedTableProgram,
    *, result_revision: int,
    scope: TableCostScope,
) -> TableCostEstimate

get_table_cost_catalog() -> TableCostCatalog
```

`TableCostScope` selecciona `material_tariff_id`, `edge_scope=none|all_exposed` y `operation_tariff_ids`; sin selección, los conceptos requeridos quedan unknown. El catálogo sintético pequeño vive en `table_costs.py`; su versión se expone. El cálculo usa ocurrencias, no vistas o tipos duplicados. Cada concepto conserva refs component/occurrence, fórmula, cantidad + `quantity_unit=m2|m3|m|unit|h`, tarifa + `rate_unit=EUR/m2|EUR/m3|EUR/m|EUR/unit|EUR/h`, importe y estado `resolved|unknown|not_applicable`. El fijo usa una tarifa catalogada con scope `preparation` y se aplica una vez; canteado solo con scope explícito; horas, operaciones y acabado ausentes siguen unknown.

Se exponen `known_subtotal_eur` y `total_state=partial|complete`; si falta un concepto requerido, `grand_total_eur=null`. Todo queda ligado a revisión/hash. El módulo no crea modelos/API.

## Semántica y biblioteca

Solo una revisión aceptada puede guardarse. La mesa usa `FurnitureDescriptorV3`/`furniture-v3`, separado de v1/v2 y sus embeddings. Incluye perfil/familia, topología, dimensiones generales, roles/cantidades y features canónicas de componentes con estados/desconocidos; excluye IDs, filename, coordenadas y evidence IDs. Caché/similitud/grupos exigen misma versión/modelo/dimensión. La similitud no decide BOM, coste o revisión.

## API aditiva

- `POST /api/v1/runs`: añade `input_kind`, `table_profile`, `proposal_mode=none|catalog_baseline|model_generated` y `table_template_id`; baseline exige template explícito, live lo prohíbe, y combinaciones incompatibles dan 422.
- `GET /api/v1/runs/{run_id}/table?result_revision=N`: análisis, programas, seleccionado y evaluación.
- `POST /api/v1/runs/{run_id}/reviews`: misma ruta/stale guard; admite revisión de mesa.
- `GET /api/v1/runs/{run_id}/scene?result_revision=N`: escena efectiva.
- `POST /api/v1/runs/{run_id}/table-drawings`: genera/persiste revisión exacta; `GET .../table-drawings?result_revision=N` solo lee manifiesto.
- `GET /api/v1/runs/{run_id}/table-drawings/{sheet_id}.{format}?result_revision=N&program_hash=...`: bytes SVG/DXF.
- `POST /api/v1/runs/{run_id}/table-costs`: calcula revisión exacta; `GET .../table-costs?result_revision=N` solo lee persistido.
- `GET /api/v1/table-cost-catalog`: catálogo sintético versionado de IDs/labels/tarifas para construir `TableCostScope`; la UI no codifica IDs.
- `GET /api/v1/config`: declara si la visión está efectivamente habilitada, su autoridad contextual y límites; nunca expone secretos.
- `GET /api/v1/runs/{run_id}/exports?format=table_cutlist`: CSV genérico revisionado de componentes/ocurrencias aceptados; declara `generic_not_certified` y conserva material/acabado/veta/cantos como unknown.
- Export JSON incluye análisis/programa raw-normalizado/revisión y scene/drawings/cost/descriptor/procedencia disponibles.
- `POST /library`, `/similarity` y `/groups` admiten `descriptor_version=furniture-v3`; consulta/grupos filtran exactamente ese espacio y pueden informar `excluded_count`. Sin filtro se conserva el comportamiento legacy, incluido el rechazo de mezcla incompatible.

Lecturas no llaman ocultamente al proveedor. Una revisión nueva invalida derivados actuales sin borrar historia. Legacy y parts-only no cambian.

## Propiedad

- A: análisis de vistas montadas, evaluación, plan geométrico y reconstrucción.
- B: modelos, API, repositorio/revisión, harness y semántica/similitud.
- Apoyo planos: `backend/app/salida/technical_drawings.py` y tests.
- Apoyo costes: `backend/app/estimacion/table_costs.py` y tests.
- C: frontend. D: fixtures y aceptación independiente.
