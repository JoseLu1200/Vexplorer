# Mejoras CAD y harness

Estado: implementado en la rama `mejoras/cad-harness`, pendiente de revisión y merge. Origen: investigación del 2026-11-14 registrada en [team/pablo.md](../team/pablo.md). El usuario autorizó expresamente los cambios de `contratos/` (regla 7 de CLAUDE.md); A y B no han intervenido y C/D no han sido avisados, por lo que la revisión del merge debe confirmarlo con ellos.

Todos los campos de contrato son opcionales y con valor por defecto: los resultados ya guardados siguen leyéndose y `schema_version` sigue en `0.2.0`.

## Aplicado

| Mejora | Dónde | Comportamiento |
|---|---|---|
| Vistas sin etiqueta de texto | `geometria/extraction.py` | Solo si no hay ninguna etiqueta. Exige exactamente tres contornos máximos con una única asignación por extensiones compartidas; si no, todo `UNKNOWN`. Marca `view_labels_inferred_from_alignment`, evidencia `view_association` y `status=needs_review`. No asume diedro. |
| Tipo de línea | `DrawingEntity.linetype`, `ingesta/dxf_reader.py` | Nombre efectivo en mayúsculas (`BYLAYER` se resuelve por la capa; `BYBLOCK` queda `None`). Solo para LINE y LWPOLYLINE. De momento es evidencia visible para el agente y la salida; ninguna regla geométrica lo usa todavía. |
| Espesor observado | `ComponentProposal.observed_thickness_mm` y `thickness_source_entity_ids`, `servicios/decomposition.py` | Líneas verticales interiores simétricas en el alzado, repetidas en la planta, a entre 3 mm y el 10 % del ancho. Solo en laterales. `thickness_mm` sigue `None`: es una observación que una persona confirma. Sin evidencia (variante incompleta) o asimétrica, se abstiene. |
| Veta y cantos | `ReviewDecision` y `ResolvedPiece`: `grain`, `edge_banding` | `None` es desconocido; `edge_banding=()` es "sin canto" confirmado. Solo por la vía de decisiones por pieza; la vía de escenario completo los deja desconocidos. |
| Lista de corte CSV | `salida/service.py`, `GET /runs/{id}/exports?format=cutlist` | Solo piezas confirmadas (422 si no hay). Vacíos y `unknown_fields` explícitos; `area_m2` y `edge_banding_m` solo con todas las entradas conocidas. Formato genérico, no de fabricante. |
| Contexto del agente | `agente/runner.py`, `agente/prompts.py` | El primer mensaje añade vistas, cotas, catálogo de evidencias, tipos de línea, detalle de propuestas y el texto del dibujo aislado y truncado como no confiable. Las claves anteriores no cambian. |
| Errores reparables | `agente/runner.py` | Las referencias desconocidas devuelven los IDs válidos; el recordatorio por falta de herramienta nombra las herramientas. |

## Aplicado en el segundo bloque (alimentación del harness)

Origen: [INVESTIGACION_ALIMENTACION_HARNESS](INVESTIGACION_ALIMENTACION_HARNESS.md). Sin cambios en `DrawingExtraction` ni en la evidencia: bloques, filas de taladros y tramas viajan como `Evidence` de tipo `geometry`. Único cambio de contrato: `VisualizeViewArgs`, aditivo y solo usado con el canal visual activado; autorizado por el usuario sin acuerdo explícito de A/B.

| Mejora | Dónde | Comportamiento |
|---|---|---|
| Bloques (`INSERT`, `MINSERT`, anidados) | `ingesta/dxf_reader.py` | Se expanden con IDs deterministas `entity-<handle>-b<i>` (`-m<k>` por celda, `-a<i>` atributos); sin `/`. Capa "0" hereda la del INSERT y `BYBLOCK` su tipo de línea. Cada visita (también INSERT y entidades no admitidas) cuenta contra el límite de entidades, y la profundidad máxima es 8 (`unsupported_block_depth`). Tras 20 avisos `unsupported_entity` el resto se resume por tipo (`unsupported_entity_more:<tipo>:<n>`). Evidencia `evidence-block-*` con el nombre del bloque marcado como no confiable. |
| Atributos (`ATTRIB`) | `dxf_reader.py`, `extraction.py` | Se leen como texto `TAG: valor` y van a `texts` (no confiable). |
| Curvas | `dxf_reader.py` | CIRCLE y ARC con 64 segmentos por vuelta; LWPOLYLINE con bulge, POLYLINE 2D, ELLIPSE y SPLINE aplanadas con tolerancia relativa. Las aproximaciones avisan con `approximated_*` y dejan `needs_review`. Formas cerradas repiten el primer punto para el visor. |
| Tramas (`HATCH`) | `dxf_reader.py`, `extraction.py` | Una entidad por frontera (`-p<i>`, no un `DrawingContour`) y evidencia `evidence-hatch-*` con el patrón. |
| Cotas por ordenadas | `dxf_reader.py`, `extraction.py` | Tipo 6: valor = distancia al origen en su eje; sin gráfico lineal (`graphic_id=None`); la vista se asigna por el punto acotado, no por el origen. |
| Paperspace, DXF dañados, unidades | `dxf_reader.py` | `paperspace_content:<layout>:<n>` (casi todo DWG real lleva el cajetín en paperspace, así que quedará en `needs_review`); reintento con `ezdxf.recover` (`recovered_dxf`); con `$INSUNITS=0`, pista `unit_hint_measurement` que nunca resuelve unidades. Todos dejan `needs_review`. |
| Filas de taladros | `geometria/extraction.py` | ≥3 círculos iguales alineados: diámetro, paso, regularidad y luz. Describe lo dibujado; no decide qué es. Solo con unidades resueltas. |
| Plausibilidad | `validador/plausibilidad.py`, `validador/catalogo_taller.json` | Compara filas con los sistemas de taladro del catálogo (por defecto solo Sistema 32: Ø5, paso 32, retranqueo 37) y el espesor observado con los tableros del catálogo (vacío hasta que lo aporte compras → `unknown`). Catálogo sustituible con `VEXPLORER_WORKSHOP_CATALOG`. Nunca rellena campos. |
| Contexto del agente | `agente/runner.py`, `agente/prompts.py` | `digest_counts` con total/mostrados/truncado; `entity_kinds`, `untrusted_layer_counts`, `circle_diameters_mm`, `hole_rows`, `block_references`, `hatches` y `plausibility_findings`. Claves anteriores intactas, salvo `evidence_ids`, que se corta a 200 (avisado en `digest_counts`). `inspeccionar_evidencia` devuelve círculos como centro y diámetro, resume curvas de más de 16 puntos y limita a 40 entidades y 20 contornos con `entity_counts`: una fila de 20 taladros pasó de ~119 000 a ~3 300 caracteres. |
| Proveedor | `agente/config.py`, `agente/provider.py` | `max_output_tokens` por `OPENAI_MAX_OUTPUT_TOKENS` (por defecto 4096, antes 1200 fijo). Una respuesta `incomplete` sigue rechazándose, ahora con el motivo. |
| Canal visual (opcional) | `agente/vision.py`, `agente/tools.py`, `main.py`, `contratos/modelos.py` | Con `VEXPLORER_AGENT_VISION=1` aparece `visualizar_vista`: PNG dibujado desde el ledger (no del DXF) con contornos numerados (Set-of-Mark) y tabla número→ID; la imagen va como mensaje `input_image` tras la salida de la herramienta. Desactivado, nada cambia. **No probado contra la API real.** |

## No aplicado y por qué

| Pendiente | Motivo |
|---|---|
| Descriptor ampliado (proporciones, baldas, puertas) | Cambiar `descriptor_version` o el texto semántico deja los embeddings guardados en espacios incompatibles (`embedding_space_incompatible`). Requiere decidir migración o recálculo. |
| Cadena de costes (canto, planchas con rendimiento, herrajes, horas) y bandas con varios comparables | Necesita tarifas y datos del taller; con el histórico sintético actual solo daría cifras inventadas. `edge_banding_m` ya queda disponible como entrada. |
| Uso de `linetype` en la geometría (aristas ocultas como evidencia de baldas, divisores, trasera) | Falta un caso con líneas discontinuas y su respuesta para calibrar. |
| Generador de casos desde PlankAssembly | `../engineering_dataset` no existe en este equipo; licencia CC BY-NC-ND y aislamiento descritos en [PLANKASSEMBLY](PLANKASSEMBLY.md). |
| Interfaz | `frontend/` no se ha tocado: no hay botón de lista de corte ni campos de veta/cantos, y el espesor observado no precarga el formulario de revisión. Corresponde a C. |
| Catálogo del taller (espesores, planchas, cantos, herrajes) | Lo debe aportar compras. |

## Qué comprobar al fusionar

- `python -m pytest -q` (166 pruebas en el entorno de la sesión tras el segundo bloque; 140 tras el primero).
- Que `backend/app/validador/catalogo_taller.json` se empaquete si se instala sin `-e` (`pyproject.toml` no declara `package-data`; no se tocó por estar fuera de alcance).
- Proveedor real con `VEXPLORER_AGENT_VISION` activado y desactivado, y con un DWG real de taller con bloques.
- `npm test --prefix frontend`: no se ejecutó en esta sesión.
- Que A y B den por bueno el cambio de `contratos/` y `geometria/`, y D el efecto en `tests/test_demo_e2e.py` (sin cambios de aserciones).
- El espesor observado procede de líneas visibles del DXF público, no de `evaluation/reference/`.
