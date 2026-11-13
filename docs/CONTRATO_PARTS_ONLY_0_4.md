# Contrato `parts-only` 0.4

Acuerdo explícito A/B del 14 de noviembre de 2026. B es el único escritor de los modelos Pydantic; A implementa extracción y reconstrucción consumiendo esos modelos. C y D fueron avisados antes de congelar el contrato.

## Entrada permitida y alcance

La entrada nueva es un DXF 2D de piezas separadas. No contiene vistas del mueble montado, planta/alzado del conjunto, roles, familia, montaje, BOM ni dimensiones generales del ensamblaje. El cliente debe enviar `input_kind=separated_part_views`; no se activa este modo silenciosamente por apariencia.

La gramática pública opcional es `PART <opaque_key> <FRONT|TOP|SIDE>` y una cantidad vinculada explícitamente a la misma key. La key asocia vistas, pero no aporta nombre, rol, material ni familia. Una cantidad suelta o una vista sin key queda ambigua. Nunca se agrupa por proximidad, nombre de archivo o número de vistas.

Los ejes locales no se ordenan por tamaño: `FRONT=(length,width)`, `TOP=(length,thickness)` y `SIDE=(thickness,width)`. Un desacuerdo entre vistas conserva el valor `null`, estado `conflict` y warning. Unidades desconocidas mantienen todas las magnitudes métricas en `null`.

## Flujo contractual

`DrawingExtraction` conserva el ledger 0.3 y añade `input_kind`. A produce:

```text
extract_separated_parts(extraction: DrawingExtraction) -> SeparatedPartsExtraction
```

`SeparatedPartsExtraction` contiene observaciones agrupadas únicamente por asociación explícita. Cada observación expone vistas y bounds locales, dimensiones `length/width/thickness`, cantidad observada o desconocida y referencias a entidades/evidencias. Varias vistas nunca incrementan cantidad.

El servicio cruza cada view/contour/entity/evidence/measurement contra el `DrawingExtraction` congelado y valida que la key procede de la gramática permitida. Un conflicto dimensional exige al menos dos vistas/evidencias incompatibles. `ambiguous` y `unassociated` nunca se fusionan por geometría o proximidad.

Los `AssemblyCandidate` son hipótesis separadas del ledger y de los escenarios legacy. Sus `uses` solo referencian observaciones, roles hipotéticos y cantidades observadas o desconocidas; `unassigned_part_observation_ids` conserva el resto y el servicio exige cobertura exacta. Una cantidad `observed_annotation` se copia exactamente de `ObservedQuantity` con la misma evidencia; `human_confirmed` solo procede de Review y `unknown` implica `source_quantity=null`, `allocated_quantity=null`, `occurrence_indices=[]`. Un mismo tipo observado puede repartirse entre roles distintos (por ejemplo tapa/base) únicamente mediante índices de ocurrencia disjuntos y exhaustivos cuya suma coincide con `source_quantity`; la key no decide el reparto. Las dimensiones `width/height/depth` del mueble son recalculadas por servidor mediante constraints con operación y operandos estructurados; nunca se confía en un resultado numérico aportado por el modelo. Se conservan permutaciones de roles y los layouts `between_sides|cap_sides` compatibles. No se inventan tapa, base, trasera, herrajes ni material.

Una revisión puede seleccionar `assembly_candidate_id` y aportar decisiones humanas por pieza. Esto crea otra revisión; no reescribe observaciones ni convierte automáticamente roles/layout/dimensiones en hechos. La escena solo crea ocurrencias cuando cantidad y `length/width/thickness` están respaldados y el placement procede de constraints estructurados del candidato seleccionado. En otro caso es `incomplete` y omite el sólido; `placement_status` distingue hipótesis de selección humana. La firma de A será:

```text
reconstruct_parts_scene(extraction: DrawingExtraction, parts: SeparatedPartsExtraction, result: Result) -> ReconstructionScene
```

## Compatibilidad y API prevista

- Los payloads 0.2/0.3 antiguos se leen con `input_kind=mounted_views_legacy` por defecto.
- `POST /api/v1/runs` añade `input_kind`; `separated_part_views` debe ser explícito.
- `GET /api/v1/runs/{run_id}` conserva el envelope y devuelve `result.part_analysis` y `result.assembly_candidates`.
- `GET /api/v1/runs/{run_id}/parts` será una vista conveniente del mismo snapshot, no otra fuente de verdad.
- `POST /api/v1/runs/{run_id}/reviews` conserva la ruta y admite `assembly_candidate_id` junto con decisiones humanas; `decisions[].proposal_id` referencia `AssemblyPartUse.id`, no la observación agregada, para confirmar por asignación/rol sin inventar mapping. No se crea un segundo sistema de revisión.
- Dibujo, explicaciones, escena, biblioteca, similitud, grupos y exportaciones permanecen ligados a `result_revision`.

El flujo nuevo usa `FurnitureDescriptorV2` (`descriptor_version=furniture-v2`), que incorpora espesores observados/confirmados y `classification_status`. Cada `part_feature` conserva un estado canónico `observed|confirmed|unknown` para longitud, ancho, espesor y cantidad; tras Review toma el valor efectivo de `ResolvedPiece` por `source_part_observation_ids`, sin mutar la observación original ni duplicar cantidades cuando un tipo se reparte entre roles. Un desconocido solo desaparece del descriptor cuando esa revisión lo resolvió explícitamente. `FurnitureDescriptor` v1 se conserva sin reinterpretarlo para leer biblioteca legacy. IDs, keys, coordenadas, filename y evidencias quedan fuera del fingerprint semántico. Embeddings v1/v2 pertenecen a espacios contractuales distintos: caché, similitud semántica y grupos incluyen la versión y rechazan mezclas. La familia y los roles permanecen `hypothesis` hasta revisión humana.

## Propiedad de implementación

- A: `backend/app/ingesta/dxf_reader.py`, `backend/app/geometria/extraction.py`, nuevo `backend/app/geometria/parts.py`, `backend/app/servicios/reconstruction.py`, pruebas geométricas y de reconstrucción parts-only.
- B: `backend/app/contratos/modelos.py`, repositorio, API/main, revisión/orquestación, harness/herramientas, descriptor/similitud y pruebas backend.
- C: frontend y pruebas de UI.
- D: fixtures públicos, referencias privadas y aceptación independiente.

`decomposition.py` legacy no se modifica para inferir piezas separadas.
