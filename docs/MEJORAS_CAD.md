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

- `python -m pytest -q` (140 pruebas en el entorno de la sesión).
- `npm test --prefix frontend`: no se ejecutó en esta sesión.
- Que A y B den por bueno el cambio de `contratos/` y `geometria/`, y D el efecto en `tests/test_demo_e2e.py` (sin cambios de aserciones).
- El espesor observado procede de líneas visibles del DXF público, no de `evaluation/reference/`.
