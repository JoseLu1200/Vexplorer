# Agente de geometría — demo local

## Identidad y autorización

- Identidad: agente de IA de geometría; no representa a una persona.
- Rol: A, ingesta y geometría determinista.
- Archivo autorizado explícitamente por el usuario en la delegación del 2026-11-13.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo actual: cerrar para producción privada la geometría, revisión repetida y planos derivados de la mesa rectangular existente, corrigiendo cuatro hallazgos reproducibles sin ampliar a geometrías arbitrarias.
- Referencia: `docs/superpowers/plans/2026-11-14-private-production.md`, Task 3, y su especificación de diseño.
- Estado: acuerdo A/B aditivo publicado antes del código; B conserva escritura exclusiva de contratos y A implementará sus consumidores cuando B confirme los nombres exactos.

## Alcance y reservas

- Puedo editar: `backend/app/ingesta/`, `backend/app/geometria/`, `backend/tests/test_geometry.py`, `tools/prepare_evaluation.py`, `tests/test_prepare_evaluation.py` y este archivo.
- La ampliación para los dos archivos del preparador fue autorizada explícitamente el 2026-11-13; ningún otro agente los edita durante esta tarea.
- Transferencia puntual autorizada tras revisión Astra: también `backend/app/servicios/decomposition.py` y la prueba nueva `backend/tests/test_decomposition_geometry.py`; B fue informado para no solapar.
- Nueva propiedad de fase: `backend/app/ingesta/`, `backend/app/geometria/`, `backend/app/servicios/decomposition.py`, nuevo `backend/app/servicios/reconstruction.py`, `backend/tests/test_geometry.py`, `backend/tests/test_decomposition_geometry.py`, nuevo `backend/tests/test_reconstruction.py` y este registro.
- Solo leeré: contratos, API, frontend, fixture público de evaluación y documentación.
- `backend/app/contratos/` pertenece exclusivamente al agente B.
- Solapes detectados: ninguno; la interfaz con B debe acordarse antes de implementación contractual.
- Nueva propiedad autorizada para mesa: nuevo `backend/app/geometria/mounted_table.py`, nuevo `backend/app/servicios/table_reconstruction.py`, el programa geométrico determinista asociado y pruebas nuevas propias de geometría/reconstrucción de mesa.
- `backend/app/salida/technical_drawings.py` pertenece al apoyo de planos y queda fuera de mi alcance; consumirá planes geométricos acordados con A/B.
- Delegación autorizada del coordinador: `/root/research_viewer` actúa como apoyo subordinado de A y posee exclusivamente el nuevo `backend/app/salida/technical_drawings.py` y sus pruebas. A coordina su interfaz y recibe sus logs, pero no edita el renderer.
- B conserva propiedad exclusiva de modelos Pydantic, API, repositorio, revisión y harness. D conserva fixtures y referencia; A no leerá `evaluation/reference/**`.

## Hecho en el último bloque

- Producción privada Task 3: reproducidos por TDD y corregidos DIMENSION con Z no nulo, ATTRIB end-to-end y discrepancia de tolerancia 0,1 mm en reconstrucción.
- Implementado gate de revisión de fuente por incidencia estable para `recovered_dxf:*`; dos avisos iguales no comparten aceptación y una contradicción física no se cierra automáticamente.
- Implementadas correcciones efectivas de slots y observaciones como capas humanas separadas; el análisis/ledger observado permanece inmutable.
- Completada la matriz de láminas: general W/D/H, componente L/W/T+cantidad+estado+procedencia y despiece L/W/T por ocurrencia; desconocidos producen `incomplete`.
- Avisados B/backend y C/frontend de los nombres contractuales y de la semántica antes de implementar consumidores.

- Leídas las reglas de coordinación, arquitectura, contratos propuestos, geometría, semántica, TDD y evaluación.
- Registrada identidad y alcance antes de editar código.
- Acuerdo A/B 0.2 cerrado explícitamente: `extract_drawing(path: Path) -> DrawingExtraction` entrega observaciones; las hipótesis viven separadas.
- Avisados C del contrato y D de las restricciones del fixture público.
- Implementado lector real `ezdxf` para LINE, LWPOLYLINE, TEXT/MTEXT y DIMENSION lineal; unidades conocidas se normalizan y las desconocidas se conservan sin mm.
- Implementadas vistas neutrales, contornos trazables, observaciones, evidencias y propuestas rectangulares genéricas con cantidad y espesor desconocidos.
- Verificados ambos DXF públicos de D sin abrir `evaluation/reference/**`: tres vistas y tres contornos; la variante incompleta expone una cota menos, sin completar el dato.
- Endurecida la honestidad: cotas angulares quedan fuera con warning; override textual o escala conflictiva conserva warning y `value_mm=null`; trapecios no producen hipótesis rectangulares; límite de 100.000 entidades se aplica antes del análisis.
- Endurecido el preparador: metadata pública uniforme sin diagnóstico de respuesta, sidecar Bench Vise sujeto a ruta segura/manifiesto/hash y lecturas fuente verificadas contra un snapshot inmutable para detectar TOCTOU.
- Corregido el servicio de descomposición: solo contornos cerrados con cuatro esquinas axis-aligned y evidencia fuente atraviesan el gate de estantería; cajas coherentes de trapecios se abstienen.
- Enriquecida la extracción con textos públicos planos, capas/posiciones, cotas lineales segmentadas y ancladas, unidades explícitas y asociación geométrica de vistas.
- Implementada reconstrucción 3D esquemática por ocurrencia física tras revisión: montaje entre/cubriendo laterales, niveles de balda observados, bbox y evidencia; estados incompletos sin sólidos inventados.
- Endurecida la escena revisada: rechaza roles duplicados, longitudes de tapa/base incoherentes y grosor/profundidad discordantes; el nivel observado se declara como cara inferior de balda.

## Siguiente bloque

- Cerrar acuerdo aditivo A/B sobre dibujo enriquecido y escena; avisar C/D; luego implementar por TDD.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-13 | Mantener cálculos puros y deterministas; separar observación, derivación e hipótesis | Reglas de arquitectura y trazabilidad | Delegación y documentación del repositorio |
| 2026-11-13 | A acepta contrapropuesta B: extracción sin propuestas; `dimensions.origin=observed|derived`; `warnings` y `synthetic`; hipótesis aparte | Evitar mezclar hechos con interpretación | Mensajes explícitos A/B y aviso posterior a C |
| 2026-11-13 | A/B acuerdan adición 0.3: `DrawingText`, `DimensionGraphic`, anclajes source/mm, escena por ocurrencia y `reconstruct_scene(extraction, result)` | Visor legible y 3D trazable sin inventar dimensiones o posiciones | Confirmación explícita de B; B único escritor de contratos; avisos C/D |

## Dependencias / avisos

- Acuerdo A/B de producción publicado el 2026-11-14 antes de modificar código: `TableConfirmedValue` añade `confirmation_id` y `supersedes_confirmation_id`; `TableObservedValueCorrection` conserva `correction_id`, `measurement_id`, valor, motivo, evidencias y corrección sustituida; `TableSourceReviewDecision` conserva warning exacto, `accept|reject` y motivo. `ReviewRequest`/`Result` llevan las dos colecciones nuevas. La revisión efectiva sustituye sólo el valor del mismo target y los `Result` previos conservan el historial; `MountedTableAnalysis` no se muta. Una contradicción mayor que 0,1 mm sigue bloqueando. Todo `recovered_dxf:*` sin `accept` explícito, o rechazado, bloquea `completed` sin borrar el warning. B es único escritor de `modelos.py`.
- Adenda Astra/A-B: `TableSourceReviewDecision.warning_id` es obligatorio y único; A deriva un ID estable por ledger, warning y ocurrencia. El evaluador publica ID+código en el blocker y exige coincidencia exacta.
- Aviso previo enviado a C: la UI debe editar confirmaciones humanas previas, mostrar valor vigente/procedencia/motivo y no convertir overrides observados ni `recovered_dxf` en aceptación automática.
- Delta económico propuesto por B aceptado por A: snapshot/versionado de catálogo, alcance tipado, horas, precio provisional con margen explícito y contribuidor por coste; no altera la geometría ni autoriza importes implícitos.

- Recibido de B: contrato aditivo 0.3 en `351fb63`, integrado como dependencia `13d18e4`; A no modificó modelos.
- Necesito de D: forma pública del fixture sin acceder a la referencia reservada ni codificar sus medidas.
- Afecta a C: IDs, unidades, contornos, cotas, vistas y propuestas que consumirá el visor.
- Aviso realizado: contrato final comunicado a frontend y fixture coordinado con evaluación el 2026-11-13.
- Aviso realizado: contrato aditivo 0.3 comunicado a frontend y evaluación el 2026-11-13.
- Cambio de `contratos/`: acuerdo A/B explícito 0.3; B es único escritor, A solo importa modelos.
- Mesa 0.5: antes de implementar, A/B deben acordar medidas, bindings, componentes, reglas de cantidad/placement, estados y recálculo desde revisión efectiva; A avisará a C, D y al apoyo de planos con las firmas finales.
- Acuerdo A/B mesa 0.5: entrada `mounted_orthographic_views` y perfil `rectangular_table_v1` explícitos; `analyze_mounted_table`, `evaluate_table_program(..., decisions)`, `derive_table_drawing_plan` y `reconstruct_table_scene`. El programa no aporta números: bindings `copy|add|subtract` referencian medidas/bindings previos; servidor valida cobertura, DAG, positividad y máximos. Dos specs de tipo (tablero + un sistema de soportes) usan registros versionados `top_one`, `two_side_supports` o `four_corner_supports` y placements asociados. Raw/normalizado/hash, evidencias y premisas quedan separados. La revisión apunta a targets exactos, recalcula una copia efectiva y no muta el ledger. Desconocidos, conflictos o medidas admitidas sin asignar bloquean completitud/escena.
- Delta A/B aceptado: `catalog_table_programs(analysis)` genera exactamente dos alternativas `catalog_baseline` incompatibles (soportes laterales o de esquina), ninguna elegida por apariencia. Los espesores/secciones ausentes son slots/premisas unknown del programa, no medidas CAD ficticias ni mediciones sin asignar.
- Adendum A/B 0.5 aceptado: todos los slots numéricos son `TableMeasure`; los requeridos por perfil se distinguen como unknown/no observados y sólo `TableConfirmedValue` humano puede resolverlos. Catálogo requiere `table_template_id` explícito. El evaluador deriva cobertura/disposiciones y bloquea conflictos; no confía en cobertura declarada por modelo. Hash topológico canónico conserva semántica de resta. Premisas y aceptaciones de programa/componente/premisa son separadas; rechazo bloquea dependientes. Cost scope y descriptor V3 quedan tipados y versionados por B.
- Cierre del adendum: antes de Review todos los bindings/componentes/placements son `proposed`, incluso si copian observaciones. Aceptar el programa valida topología/bindings y permite `calculated`, pero no acepta componentes ni premisas. Las premisas iniciales son siempre requeridas por registry; perfil, revisión de ledger y origen los inyecta servidor, no la herramienta del modelo.
- Delta CAD A/B aceptado: `DrawingEntity.linetype` conserva el tipo de línea efectivo y `CircularGeometry` conserva CIRCLE/ARC exactos (centro, radio y ángulos) sin presentar muestras discretizadas como geometría exacta. A mantiene propiedad de reader/extraction; B fue único escritor del contrato `f8c8fb4`.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| Geometría + contrato | `python -m pytest backend/tests/test_geometry.py backend/tests/test_backend_contract.py -q` | 9 passed | Fixture público de D aún no integrado |
| Fixture público | `extract_drawing` sobre ambos `data/planos_demo/*.dxf` | montada: ready/mm, 3 vistas, 3 contornos, 4 cotas; incompleta: ready/mm, 3 vistas, 3 contornos, 3 cotas | La revisión semántica vive en hipótesis/escenario, no en la salud de ingesta |
| Suite completa tras fixture | `python -m pytest -q` | 30 passed | Incluye 8 pruebas de aislamiento/fixture de D |
| Regresiones de revisión | `python -m pytest backend/tests/test_geometry.py -q` | 10 passed | Angular, texto/escala, trapecio y límite cubiertos |
| Suite final | `python -m pytest -q` | 35 passed | Ejecución fresca tras correcciones |
| Preparador | `python -m pytest tests/test_prepare_evaluation.py -q` | 17 passed | Incluye ZIP público y tamper de bytes/ruta/manifiesto |
| Suite tras preparador | `python -m pytest -q` | 39 passed | Baseline, geometría y demo permanecen verdes |
| Auditoría corpus local | `python -m tools.prepare_evaluation --source ../../../engineering_dataset --audit-only` | 421 archivos, 65 casos, 93 rutas; manifiesto `60b45a…` | Solo auditoría; no se regeneró ni publicó corpus |
| Gate de descomposición | `python -m pytest backend/tests/test_decomposition_geometry.py backend/tests/test_backend_flow.py -q` | 6 passed | Rechaza tres trapecios coherentes y mantiene W/D/H rectangular existente |
| Suite tras gate | `python -m pytest -q` | 50 passed | Incluye backend integrado; creó `.vexplorer-data/` local no versionado |
| Contrato y dibujo 0.3 | `python -m pytest backend/tests/test_geometry.py backend/tests/test_backend_contract.py backend/tests/test_backend_contract_viewer.py -q` | 23 passed | Texto se conserva como dato; el frontend debe usar `textContent` |
| Reconstrucción | `python -m pytest backend/tests/test_reconstruction.py backend/tests/test_geometry.py -q` | 20 passed | Cajas esquemáticas, colisiones no evaluadas |
| Suite fase visor | `python -m pytest -q` | 69 passed | Ejecución fresca antes de commits A |
| Hardening escena | `python -m pytest backend/tests/test_reconstruction.py -q` | 8 passed | Incluye cambio de montaje en revisión 3 e incoherencias de revisión |
| Suite final A | `python -m pytest -q` | 72 passed | Ejecución fresca tras hardening |
| Sintaxis/diff | `python -m compileall -q backend/app/ingesta backend/app/geometria`; `git diff --check` | pasa sin salida | No sustituye prueba E2E |
| CAD montado endurecido | `python -m pytest backend/tests/test_ingesta_cad_geometry.py backend/tests/test_mounted_view_inference.py backend/tests/test_geometry.py backend/tests/test_mounted_table_geometry.py backend/tests/test_table_reconstruction.py -q` | 37 passed | Inferencia sólo para triple ortográfico único; curvas no circulares siguen fuera del subconjunto |
| Baseline Task 3 producción | suite geométrica focal | 76 passed | Antes de las nuevas regresiones |
| RED auditoría Task 3 | cuatro nodos independientes | 4 failed esperados | DIMENSION Z, ATTRIB, tolerancia y espesor en despiece |
| Geometría/planos producción | ingesta, geometría, parts, reconstrucción, mesa y renderer | 83 passed | Incluye blockers por incidencia y láminas incompletas honestas |
| Reconstrucción parts tolerante | `python -m pytest backend/tests/test_parts_reconstruction.py -q` | 9 passed | `+0,05 mm` permanece dentro de 0,1 mm |
| Integración geometría + repository | tests de repository mesa, geometría mesa y reconstrucción parts | 30 passed | Incluye cadena de corrección r2→r3 con histórico intacto |
| Suite Python completa producción | `python -m pytest -q` | 378 passed; 1 warning | Warning deprecado Starlette TestClient/httpx |
| Sintaxis/diff Task 3 | `python -m compileall -q ...`; `git diff --check -- <rutas propias>` | pasa | Ruff ausente del entorno (`No module named ruff`) |

## Bloqueos y cierre

- Bloqueos: ninguno para el alcance propio.
- Pendientes: B integra endpoint de escena; C consume textos/cotas/escena; D ejecuta aceptación independiente.
- Límites: modelspace; subconjunto LINE/LWPOLYLINE recto/CIRCLE/ARC exactos/TEXT/MTEXT/ATTRIB/DIMENSION lineal; bloques anidados 2D se expanden con profundidad y cantidad acotadas. Bulges, ELLIPSE/SPLINE/HATCH y paperspace siguen fuera del subconjunto; no se proyectan entidades con Z no nulo. Escena solo para roles y dos montajes admitidos tras revisión; no trasera, material, mecanizados, colisiones certificadas ni sólidos de fabricación.
- Reservas liberadas: ninguna.
