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

Los `AssemblyCandidate` son hipótesis separadas del ledger y de los escenarios legacy. Sus `uses` solo referencian observaciones, roles hipotéticos y cantidades observadas o desconocidas. Las dimensiones `width/height/depth` del mueble son derivadas mediante constraints estructurados; no proceden de cotas del conjunto. Se conservan permutaciones de roles y los layouts `between_sides|cap_sides` compatibles. No se inventan tapa, base, trasera, herrajes ni material.

Una revisión puede seleccionar `assembly_candidate_id` y aportar decisiones humanas por pieza. Esto crea otra revisión; no reescribe observaciones. La escena solo crea ocurrencias cuando cantidad y `length/width/thickness` están respaldados por observación o confirmación humana. En otro caso es `incomplete`. La firma de A será:

```text
reconstruct_parts_scene(extraction: DrawingExtraction, parts: SeparatedPartsExtraction, result: Result) -> ReconstructionScene
```

## Compatibilidad y API prevista

- Los payloads 0.2/0.3 antiguos se leen con `input_kind=mounted_views_legacy` por defecto.
- `POST /api/v1/runs` añade `input_kind`; `separated_part_views` debe ser explícito.
- `GET /api/v1/runs/{run_id}` conserva el envelope y devuelve `result.part_analysis` y `result.assembly_candidates`.
- `GET /api/v1/runs/{run_id}/parts` será una vista conveniente del mismo snapshot, no otra fuente de verdad.
- `POST /api/v1/runs/{run_id}/reviews` conserva la ruta y admite `assembly_candidate_id` junto con decisiones humanas; no se crea un segundo sistema de revisión.
- Dibujo, explicaciones, escena, biblioteca, similitud, grupos y exportaciones permanecen ligados a `result_revision`.

El descriptor canónico incorpora espesores observados/confirmados y `classification_status`; IDs, keys, coordenadas, filename y evidencias quedan fuera del fingerprint semántico. La familia y los roles permanecen `hypothesis` hasta revisión humana.

## Propiedad de implementación

- A: `backend/app/ingesta/dxf_reader.py`, `backend/app/geometria/extraction.py`, nuevo `backend/app/geometria/parts.py`, `backend/app/servicios/reconstruction.py`, pruebas geométricas y de reconstrucción parts-only.
- B: `backend/app/contratos/modelos.py`, repositorio, API/main, revisión/orquestación, harness/herramientas, descriptor/similitud y pruebas backend.
- C: frontend y pruebas de UI.
- D: fixtures públicos, referencias privadas y aceptación independiente.

`decomposition.py` legacy no se modifica para inferir piezas separadas.
