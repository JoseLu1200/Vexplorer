# Agente backend — demo local

Identidad: agente B de IA; no representa a una persona. Autorización: solicitud explícita del usuario del 2026-11-13.

## Alcance y propiedad

- Único escritor de `backend/app/contratos/`.
- Backend salvo ingesta y geometría: `backend/app/api/`, `agente/`, `herramientas/`, `validador/`, `salida/`, `servicios/`, `backend/app/main.py` y `backend/app/__init__.py`.
- Configuración y pruebas propias: `pyproject.toml`, `.env.example`, `backend/tests/test_backend*.py`.
- Alcance adicional autorizado por coordinación: `backend/app/historico/` y `backend/app/estimacion/`.
- No editar `backend/app/ingesta/`, `backend/app/geometria/`, `frontend/`, `evaluation/`, `data/planos_demo/` ni archivos reservados a otros agentes.

## Tarea

Implementar el backend local completo de la primera demo: contrato Pydantic 0.2 acordado con A y comunicado a C/D; API FastAPI y persistencia local; revisión versionada; herramientas y bucle live configurable; modo `geometry_only`; comparables sintéticos; estimación explicada; exportación; pruebas de comportamiento sin red.

## Dependencias / avisos

- Bloqueo inicial: acordar con `/root/geometria` la interfaz `extract_drawing` y los modelos 0.2 antes de implementar contratos; avisar a `/root/frontend` antes de escribirlos.
- El fixture y los oráculos pertenecen a `/root/evaluacion`; el backend no leerá la referencia reservada ni codificará sus valores en extractor o prompt.
- El frontend pertenece a C y será servido por FastAPI sin modificar sus archivos.

## Estado

Vertical slice backend completo y verificado; pendiente únicamente integrar los commits en la rama coordinadora y repetir el recorrido navegador del equipo.

## Registro de trabajo

- 2026-11-13: identidad, alcance, dependencias y bloqueo contractual registrados antes de editar código.
- 2026-11-13: acuerdo explícito A/B 0.2: `extract_drawing(path: Path) -> DrawingExtraction`; geometría entrega solo observaciones/evidencia, sin propuestas; B mantiene escenarios hipotéticos y revisiones separadas. C y D avisados antes de implementar.
- 2026-11-13: consultada documentación oficial de OpenAI Responses/function calling; el adaptador live usará herramientas estrictas y correlación por `call_id`, sin herramientas integradas ni acceso libre a archivos.
- 2026-11-13: commit contractual `3346537`; `python -m pytest backend/tests/test_backend_contract.py -q` → 4 passed. Compartido con A/C/D.
- 2026-11-13: commits integrados de A/D para verificar extractor y fixture reales: `427b9c0`, `1130b4e`, `8c40471`, `f346c77`; no son autoría de B.
- 2026-11-13: commit servidor `df184a9`: upload DXF, escenarios incompatibles, revisión versionada, histórico sintético, estimación por conceptos, export, SSE, frontend estático y live configurable.
- 2026-11-13: commit hardening `a7ce394`: anti-traversal, dimensiones ortográficas consistentes, export bundle auditable, eventos de revisión/estimación, revisión atómica, tarifa compatible y herramientas live con evidencia vectorial estructurada.
- 2026-11-13: `python -m pytest -q` → 45 passed. Smoke live real con `gpt-6.1-sol` y fixture público → HTTP 201, resultado `needs_review`, dos escenarios; sin fallback ni exposición de secretos.

## Límites reales

- Modalidad live: evidencia vectorial estructurada, no visión ni imagen; la persona confirma escenario, espesor, material y acabado.
- Catálogo, costes y tarifas son sintéticos y se etiquetan como tales; horas permanecen desconocidas.
- `recorded_replay` se rechaza hasta disponer de una grabación real autorizada.
- Persistencia SQLite local de un host; sin promesa de alta disponibilidad ni autenticación multiusuario en esta demo.

## Ampliación visor, reconstrucción y similitud — 2026-11-13

- Rama propia `demo/viewer-backend`, base `56faba4`.
- Propiedad B: contratos (único escritor), API, harness, repositorio, explicaciones, descriptor semántico y similitud. Fuera de alcance: `decomposition.py` y `reconstruction.py` (A), frontend (C) y fixture/evaluación (D).
- Acuerdo explícito A/B 0.3 previo a código: `DrawingText`, `DimensionGraphic`, campos aditivos retrocompatibles de `DrawingExtraction`, `SceneObject`, `ReconstructionScene` y `reconstruct_scene(extraction, result)`. C y D avisados antes de implementar.
- Descriptor canónico versionado sin IDs/rutas/nombre/traslación; vector geométrico etiquetado separado del embedding real. Biblioteca conserva la última revisión de cada run y excluye duplicados de revisión.
- Embeddings OpenAI explícitos con `text-embedding-3-small`, dimensión configurable, caché por descriptor/modelo/dimensión/versión y errores visibles. El modo offline nunca se presenta como embedding semántico.
- Cierre 0.4: A/B acuerdan que `FurnitureDescriptorV2.part_features` representa por campo `observed|confirmed|unknown`; una revisión puede completar cantidad/espesor en el descriptor efectivo sin alterar `SeparatedPartObservation`, agregando allocations por observación sin doble conteo.
- Estado inicial: documentación obligatoria y guía oficial de embeddings leídas; contrato acordado y endpoints propuestos; todavía sin cambios de producto.

## Cambio de fundamento `parts-only` — 2026-11-14

- Rama `feat/parts-backend` desde `main` `dab7ce5`.
- Nueva entrada: exclusivamente DXF 2D de piezas separadas; no se reutilizan vistas del mueble montado como evidencia.
- Acuerdo explícito A/B 0.4 previo a código: `extract_separated_parts(extraction) -> SeparatedPartsExtraction`, cantidades nullable, agrupación solo por key pública explícita, ejes locales fijos sin ordenar, candidatos de ensamblaje hipotéticos separados y reconstrucción posterior a revisión.
- B mantiene contratos, API/repositorio/revisión/harness/semántica. A mantiene ingesta, geometría parts-only y reconstrucción; `decomposition.py` legacy no participa.
- C y D avisados del shape antes de implementar. Contrato escrito en `docs/CONTRATO_PARTS_ONLY_0_4.md`.

## Mesa desde vistas montadas y planos derivados — 2026-11-14

- Rama `feat/table-backend` desde `main` `164356b`.
- B es único escritor de `backend/app/contratos/modelos.py`, y propietario de API/main, repositorio, harness y la integración semántica/similitud de este hito.
- A conserva geometría montada, evaluación del programa y reconstrucción de mesa. B no editará esos módulos.
- Agente de apoyo IA `/root/research_viewer`: propiedad exclusiva de `backend/app/salida/technical_drawings.py` y sus pruebas; B acuerda la firma y consume su salida, sin editar esos archivos.
- Agente de apoyo IA `/root/research_harness`: propiedad exclusiva de `backend/app/estimacion/table_costs.py` y sus pruebas; B acuerda la firma y consume su salida, sin editar esos archivos. Sus avances se registran aquí por B.
- Bloqueo contractual activo: acuerdo explícito A/B 0.5 y `docs/CONTRATO_MESA_0_5.md` deben preceder cualquier cambio de modelos o producto. C, D y ambos apoyos recibirán el contrato congelado.
- Transferencia puntual autorizada por coordinación a `/root/integracion_cad`: propiedad exclusiva de `backend/app/validador/plausibilidad.py`, `backend/app/validador/catalogo_taller.json` y `backend/tests/test_validador_plausibilidad.py`. B no editará esos archivos. El validador queda interno hasta acordar un modelo público; debe devolver unknown para catálogo ausente/no confirmado y validar todas las restricciones configuradas antes de pass.
- Transferencia puntual autorizada por coordinación a `/root/integracion_cad`: propiedad exclusiva de `backend/app/agente/vision.py` y `backend/tests/test_agente_vision.py`, con renderer PNG acotado por vista y marcas ligadas al ledger. B conserva config/provider/runner; la visión queda opt-in y nunca sustituye medidas validadas.
- Transferencia puntual a `/root/research_harness`: propiedad exclusiva de `backend/app/salida/table_cutlist.py` y `backend/tests/test_table_cutlist.py`, con firma pura acordada y sin veta/cantos/material inventados. B conectará la API tras integrar su commit.
- 2026-11-14: aditivo visual comunicado a A y C antes del cierre. `VisualizeTableViewArgs` es la única entrada de la herramienta nativa `visualizar_vista`; solo se anuncia en mesa con opt-in servidor. El renderer usa ledger/CircularGeometry, tiene presupuestos previos a raster y la imagen no autoriza medidas. C no necesita cambiar payloads de run/review; puede leer capacidad y trazas allowlist desde la API.
