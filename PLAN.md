# Vexplorer — plan de implementación

> **Implementación futura.** Leer primero [CLAUDE.md](CLAUDE.md), [initial-plan.md](initial-plan.md) y [team/README.md](team/README.md). Antes de editar código, cumplir el protocolo de identidad, archivo personal y alcance. Las casillas no acreditan trabajo completado ni aprobación del contrato.

**Objetivo:** interpretar vistas 2D pobres de un mueble, proponer piezas y secciones revisables y orientar tiempos y presupuesto mediante muebles históricos similares. La extracción de cotas es el primer hito, no la prueba de concepto completa. Requisitos y evaluación en [CASO_DE_USO_Y_EVALUACION](docs/CASO_DE_USO_Y_EVALUACION.md), derivados de la [transcripción](transcripcion-contexto-poc.md).

**Alcance de las prioridades:** P0 y los contratos 0.1.0 describen el hito técnico T1–T10. T11–T13 son necesarias para la prueba de concepto de negocio, aunque requieran ampliar esos contratos. El histórico y la inferencia desde planos pobres no se aplazan como mejoras opcionales.

**Arquitectura:** geometría determinista antes del LLM; libro de evidencias inmutable; herramientas nativas; validación común para entrega y revisión. HTTP/SSE conecta FastAPI con plano, tabla, traza y cajas esquemáticas.

**Stack propuesto:** Python 3.11 o posterior compatible, FastAPI, Pydantic 2, ezdxf, SQLite, proveedor LLM configurable mediante adaptador nativo; JS/HTML y three.js. Fijar versiones al implementar; la auditoría incluida usó ezdxf 1.4.4. Shapely es opcional para operaciones 2D que se justifiquen. No hace falta GPU, LangChain ni entrenamiento de pesos.

**Especificación:** [ARQUITECTURA](docs/ARQUITECTURA.md), [CONTRATOS_DATOS](docs/CONTRATOS_DATOS.md), [HARNESS](docs/HARNESS.md), [DATASET](docs/DATASET.md).

## Restricciones globales

- Contrato propuesto `schema_version=0.1.0`, pendiente de acuerdo explícito A/B y aviso C. Pydantic será la única fuente; generar los esquemas desde sus modelos.
- DXF P0; DWG/ODA P1 salvo conversor instalado y comprobado. PDF de entrada es un piloto P1 separado; STEP queda como referencia de evaluación, sin acceso del agente en el modo solo plano.
- Valores métricos en mm solo después de resolver unidades. Unidades ausentes → revisión.
- `entity_level=object|part|unknown`; solo `part` puede entrar en `pieces`.
- Tres observaciones pueden representar una sola pieza. Cantidad ambigua → `null`.
- Medidas y geometría inmutables; el agente entrega referencias, no cifras libres.
- `max_model_calls=15`, `max_tool_calls=30`, `max_validation_repairs=2`, `run_timeout_s=120`.
- `ingest_timeout_s=60`, `oda_timeout_s=30` incluido; `max_upload_bytes=20971520`, `max_entities=100000`.
- `abs_tol_mm=0.1`, `rel_tol=1e-6`: comparación numérica, no tolerancia de fabricación.
- Colisión física genérica y cadenas generales R-015 en P0 → `not_applicable`; no usar solapamientos 2D ni sumar cotas sin premisas estructuradas.
- Modos `live|geometry_only|recorded_replay` visibles; el replay nunca se presenta como ejecución nueva.
- El corpus real no se publica como archivos CAD en este paquete o repositorio.

## Foco de revisión transversal

1. Orla contiene 11 DXF sin unidad declarada y 3 en mm. T2 debe conservar unidades desconocidas; no inferirlas del STEP ni del catálogo de respuestas. T3 separa longitud geométrica, valor almacenado, escala y texto visible, como en handle `5319` de SLOTTED RIB BRACKET.
2. Geometría dentro de bloques y grafismos de cotas: T2/T3 deben expandir con procedencia y separar flechas/texto de piezas.
3. Los 14 CAD son piezas mecánicas aisladas y los conjuntos están en PDF: T4 no los convierte en una BOM de muebles. Despiece de paneles se prueba con fixture propio; cero candidatas genera un resultado revisable, no éxito vacío.
4. Cancelación o reconexión durante una entrega: T6/T7 deben impedir doble finalización y conservar orden de eventos.
5. Corrección humana tras fin del run: T6/T8 deben versionar Result y mantener el Run histórico; no editar el libro.

Cada punto tiene un test concreto en su tarea. El catálogo extenso no sustituye fixtures de borde controlados.

## Rutas, propiedad y orden

Las rutas siguientes son **futuras**. Se crearán durante implementación; este paquete entrega sus especificaciones y ejemplos.

| Tarea | Propietario sugerido | Depende de | Resultado revisable |
|---|---|---|---|
| T1 Contratos y fixtures | B + A | Documentación | Tipos y oráculos mínimos |
| T2 Ingesta y normalización | A | T1 | Archivo y entidades trazables |
| T3 Cotas y vistas | A | T2 | Libro de evidencias geométricas |
| T4 Candidatas y significado | A + B | T3 | Hipótesis e identidad explícitas |
| T5 Validador y resolución | B | T1/T4 | Resultado desde referencias |
| T6 Persistencia y API | B | T1; integra T5 | Ejecuciones y eventos recuperables |
| T7 Harness | B | T5/T6 | Bucle acotado y entrega idempotente |
| T8 Plano, tabla y revisión | C | T1; integra T3/T6 | Recorrido visual coherente |
| T9 Exportación y cajas | C + B | T5/T8 | Archivos y representación fiel |
| T10 Demo técnica | Todo el equipo | T2–T9 | Extracción y errores ensayados |
| T11 Corpus e inferencia de despiece | A + B; D si existe | Selección de datos desde el inicio; integra T1–T9 | Plano pobre, referencia oculta y propuestas revisables |
| T12 Histórico y estimación | B + A + C | Catálogo desde el inicio; integra T11 | Comparables y cálculo de costes/horas trazable |
| T13 Aceptación de negocio | Todo el equipo | T11/T12 | Evaluación reservada y ficha útil para compras |

T6 y T8 pueden empezar contra ejemplos sintéticos explícitos tras T1. No afirmar integración real hasta conectar los productores reales. [ORGANIZACION](ORGANIZACION.md) establece quién modifica contratos compartidos.

## Convención de TDD y comandos

En cada tarea: test primero, observar fallo por el comportamiento ausente, implementar lo mínimo, ejecutar, refactorizar y registrar evidencia. Si una interfaz no existe, hacerla importable con el mínimo necesario para observar el comportamiento fallido; no confundir un import roto con un oráculo numérico.

Los comandos siguientes se ejecutan **cuando exista el proyecto**, desde `backend/` o `frontend/` según se indique. No han sido ejecutados sobre una aplicación Vexplorer. Configurar los scripts de frontend `test` y `test:e2e` en T8; no asumir que ya están disponibles. La suite Python no requiere claves de proveedor para pruebas ordinarias.

## T1 — Contratos y casos mínimos

**Crear:** `backend/app/contratos/modelos.py`, `backend/tests/contract/test_contracts.py`, `backend/tests/fixtures/manifest.json`, `backend/tests/fixtures/builders.py`. Revisar los ejemplos de [EJEMPLOS_CONTRATO](docs/EJEMPLOS_CONTRATO.md). Responsable B con acuerdo explícito de A y aviso C antes de escribir los modelos; dejar ese acuerdo registrado.

**Interfaces:** modelos `EvidenceLedger`, `Submission`, `ValidationReport`, `Result`, `RunConfig`; tipos internos `ActorContext` (ámbito y autoridad), `Limits`, `RunOutcome`, `ParsedDrawing`, `NormalizedDrawing`. Definir los internos junto a su módulo; nunca enviarlos completos al proveedor.

- [ ] Escribir `test_submission_rejects_free_numeric_dimensions`: aceptar los IDs de ejemplo y rechazar el mismo campo sustituido por `600`, así como `additionalProperties` no admitidas.
- [ ] Ejecutar `python -m pytest tests/contract/test_contracts.py -q`; observar el fallo y su motivo.
- [ ] Crear modelos Pydantic, validación de finitud y rechazo de campos extra. Generar JSON Schema desde esos modelos para las herramientas; comprobar que el adaptador del proveedor no debilita la validación del servidor.
- [ ] Pasar el test; añadir `test_unknown_thickness_is_null` y `test_non_part_cannot_be_published_as_piece`.
- [ ] Preparar fixtures propios con coordenadas y valores esperados anotados manualmente: rectángulo 600×400 mm, segmento de 1 pulgada, balda de tres vistas y variante incompleta. Los builders crean entradas; no calculan los valores esperados con el extractor.
- [ ] Ejecutar la suite de contrato, revisar los ejemplos con A/C y hacer commit del entregable.

**Aceptación:** campos y enums únicos para productor/consumidor; ejemplo de tres vistas con cantidad 1; ningún CAD de terceros incorporado al repositorio público.

## T2 — Ingesta, unidades y bloques

**Crear:** `backend/app/ingesta/service.py`, `dxf_reader.py`, `oda_converter.py`; `backend/app/geometria/normalization.py`; `backend/tests/unit/test_ingest.py`, `test_units.py`, `test_block_transforms.py`.

**Interfaces:** `parse_dxf(path: Path, config: RunConfig) -> ParsedDrawing`; `normalize_drawing(drawing: ParsedDrawing, config: RunConfig) -> NormalizedDrawing`; resultado tipado de revisión para unidades o geometría no soportada. `convert_dwg(path: Path, deadline: float) -> ConversionManifest` es P1; P0 debe devolver indisponibilidad explícita.

- [ ] Escribir tests para 1 in→25.4 mm, 1 m→1000 mm, unidad ausente→revisión; conservar valor fuente.
- [ ] Añadir `test_insert_preserves_instance_path`: segmento local de 100 mm, escala 2, giro 90°, traslación (10,20) → extremos (10,20)/(10,220), longitud 200; dos instancias mantienen IDs distintos.
- [ ] Ejecutar esos tests y observar fallos; implementar normalización y manifiesto sin cambios destructivos al original.
- [ ] Separar alcanzabilidad de bloques geométricos y bloques gráficos de cotas; probar que una flecha escalada de DIMENSION no se convierte en componente ni rechaza el dibujo completo.
- [ ] Añadir fronteras 20 MiB/100000 entidades, formato inválido, rutas de archivo controladas, bloques cíclicos y expansión acotada. Un límite de archivo no sustituye validación del contenido.
- [ ] Pasar tests específicos, suite afectada y revisión de A/B. Registrar versiones y commit.

**Aceptación:** se leen las muestras elegidas sin perder jerarquía ni identidad; unsupported se informa. Los casos de escala no uniforme y reflexión se verifican mediante fixtures propios y se inventarían por separado en las muestras admitidas, sin asumir soporte por parseo correcto.

## T3 — Cotas, contornos y vistas

**Crear:** `backend/app/geometria/contours.py`, `dimensions.py`, `views.py`; `backend/tests/unit/test_dimensions.py`, `test_contours.py`, `test_views.py`.

**Interfaces:** `extract_measurements(drawing: NormalizedDrawing) -> list[Measurement]`; `extract_views(drawing: NormalizedDrawing) -> list[View]`; `extract_contours(drawing: NormalizedDrawing, views: list[View]) -> list[Contour]`. Devolver también evidencias y cobertura mediante un resultado interno tipado, sin listas desconectadas de procedencia.

- [ ] Escribir `test_dimension_without_actual_measurement`: cota de una longitud 1.535 en metros, `text="<>"`, factor 1 → 1535 mm sin exigir el atributo opcional. Usar fixture propio: este caso no describe una cota verificada del dataset actual.
- [ ] Escribir conflicto 600 geométrico/620 texto sobrescrito: conservar ambas evidencias y estado `conflict`. Añadir un caso de escala conocida con valor geométrico, almacenado y mostrado distintos, sin aplicar el factor dos veces.
- [ ] Inventariar por separado cotas angulares y `ARC_DIMENSION`; no convertir grados a mm ni afirmar cobertura de las 374 cotas cuando se evalúan solo las 370 `DIMENSION`.
- [ ] Probar rectángulo 600×400 rotado: dimensiones locales invariantes; la caja global no es la medida final.
- [ ] Observar fallos, implementar el subconjunto de cotas/primitivas y separar anotaciones de contornos candidatos.
- [ ] Probar paperspace 1:10 sin reducir medidas de modelspace; registrar su exclusión P0. Una vista no identificada no obtiene orientación por orden de dibujo.
- [ ] Ejecutar tests y revisar tres medidas con otra persona usando el plano original; registrar resultados y commit.

**Aceptación:** toda medida tiene origen, marco, unidad y evidencia. La vista previa puede mostrar cotas generales aunque no exista despiece.

## T4 — Candidatas, identidad y semántica

**Crear:** `backend/app/geometria/candidates.py`; `backend/app/agente/semantica/features.py`, `similarity.py`, `relations.py`; `backend/tests/unit/test_candidates.py`, `test_semantics.py`.

**Interfaces:** `build_ledger(drawing: NormalizedDrawing) -> EvidenceLedger`; `comparar_candidatas(ledger: EvidenceLedger, candidate_ids: tuple[str, str]) -> ComparisonResult`. Congelar la revisión solo tras terminar el libro.

- [ ] Escribir caso tres observaciones asociadas→una candidata física; variante sin asociación→`identity_status=ambiguous`, cantidad sin confirmar.
- [ ] Escribir `test_whole_furniture_is_not_a_panel`: el contorno de una mesa completa puede conservar nombre/contexto, pero no se entrega en `pieces`.
- [ ] Escribir igual envolvente y taladros distintos→variantes separadas; alternativas de una misma ocurrencia no son cantidades aditivas. El contrato técnico 0.1.0 no expresa una pieza frente a tres piezas: conservar la ambigüedad. T11 debe incorporar escenarios de descomposición y revisión de identidad antes de declarar cubierta la prueba de concepto.
- [ ] Observar fallos; implementar reglas geométricas y recuperación de ejemplos antes de introducir clasificación neural adicional.
- [ ] Mantener pistas de catálogo separadas (`metadata_mode`); el test ciego no recibe slug, título ni categoría que revelen la respuesta.
- [ ] Ejecutar tests, revisar asociaciones y commit. Congelar dev/test antes de medir calidad semántica.

**Aceptación:** distinguir parecido, misma pieza, misma geometría y posible equivalencia de fabricación. Desconocidos conservados; ninguna ampliación silenciosa de alcance por el tamaño del dataset.

## T5 — Validador y resolución numérica

**Crear:** `backend/app/validador/rules.py`, `service.py`; `backend/tests/unit/test_validation.py`, `test_derivations.py`.

**Interfaces:** `validate_submission(ledger: EvidenceLedger, submission: Submission, actor: ActorContext) -> ValidationReport`; `resolve_result(ledger, submission, report, mode, result_revision) -> Result`. Usar los tipos de T1 y reglas R-001…R-018 propuestas.

- [ ] Escribir R-015→`not_applicable` en P0, solapamiento 2D→colisión `not_applicable`, espesor ausente→`null`. El positivo 18+564+18=600 y la discrepancia 4 mm quedan en P1 tras acordar una representación estructurada de cadena y marco.
- [ ] Escribir abstención: ledger íntegro con candidatas→`pieces=[]` y disposición de revisión por candidata; ledger vacío→R-018/no_supported_part_candidates y `needs_review`; ledger con referencias rotas→`failed/invalid_evidence_ledger`.
- [ ] Escribir referencias inexistentes, revisión obsoleta, candidatas omitidas/duplicadas, cantidad incorrecta y confirmación semántica sin autoridad→rechazo.
- [ ] Ejecutar tests rojos, implementar reglas y resolución desde referencias, sin permitir modificaciones al ledger.
- [ ] Probar derivaciones con aridad, orden, ciclos y constante; `difference(600,36)=564`, no ejecutar texto arbitrario.
- [ ] Ejecutar la suite; segunda revisión de reglas y commit.

**Aceptación:** JSON válido no equivale a pieza válida; todos los resultados incluyen comprobaciones aplicadas y no aplicables. No usar otro modelo como árbitro final de los números.

## T6 — Persistencia, API y eventos

**Crear:** `backend/app/api/repository.py`, `backend/app/api/routes.py`, `events.py`; `backend/tests/integration/test_runs_api.py`, `test_events.py`, `test_review.py`.

**Interfaces:** repositorio con `create_run`, `claim_run`, `append_event`, `finalize_once`, `cancel_once`, `create_result_revision`. Cada operación mutante define transacción y comparación de estado/revisión. API y sobres exactos en [API_Y_EVENTOS](docs/API_Y_EVENTOS.md).

- [ ] Escribir flujo upload→201 document→202 run→consulta; GET ledger/drawing con revisión coincidente y mapeo de IDs. Eventos 1,2,3,4 y reconexión desde 2→3,4.
- [ ] Escribir abstención persistida como Result revisión 1 y revisión humana posterior; comprobar que el borrador inválido del modelo no entra en el resultado.
- [ ] Escribir ambos órdenes de finalización/cancelación concurrente: un único estado terminal, sin commit parcial.
- [ ] Escribir revisión humana: `base_result_revision` vigente crea revisión 2; obsoleta no altera estado; Run terminal original permanece igual.
- [ ] Observar fallos; implementar SQLite, worker controlado, eventos persistidos y autorización por documento/run.
- [ ] Probar reinicio: run interrumpido queda `failed` con causa; no reanudación simulada. Desconectar SSE no cancela.
- [ ] Ejecutar pruebas de integración y commit.

**Aceptación:** resultados y traza sobreviven a recarga, sin afirmar alta disponibilidad. CPU y conversión no bloquean el event loop.

## T7 — Harness nativo y contingencias

**Crear:** `backend/app/agente/provider.py`, `runner.py`, `prompts.py`, `cache.py`; `backend/app/herramientas/tools.py`; `backend/tests/unit/test_harness.py`, `test_tools.py`, `test_cache.py`.

**Interfaces:** `run_agent(run_id, ledger, provider, repository, limits, clock) -> RunOutcome`; adaptador normaliza llamadas nativas con IDs correlacionados. Herramientas exactas en [HARNESS](docs/HARNESS.md). El proveedor falso solo sustituye la frontera externa.

- [ ] Escribir secuencia controlada inspeccionar→borrador inválido→referencia corregida→entregar; afirmar resultado resuelto y ledger sin cambios.
- [ ] Escribir dato inexistente→revisión, sin agotar llamadas intentando inventarlo; respuesta textual sin herramienta final no se publica. Si no hay propuesta aceptable, construir y validar abstención del servidor antes de persistir `needs_review`.
- [ ] Probar máximos 15 intentos/30 herramientas/2 reparaciones y deadline 120 s con reloj controlado; la operación siguiente al límite no empieza.
- [ ] Implementar bucle, cancelación cooperativa, errores tipados y finalización transaccional. Mismo Submission entregado dos veces retorna resultado existente.
- [ ] Probar cambios de fingerprint y `geometry_only`/`recorded_replay` con modo/origen visibles. Tokens/errores del proveedor se registran cuando existen; no inventar coste.
- [ ] Ejecutar suite. Solo después, prueba de humo optativa con una clave configurada y presupuesto acotado; informar por separado. Commit.

**Aceptación:** el harness usa la misma validación que T5 y no concede permisos por instrucciones del CAD.

## T8 — Plano, tabla, revisión y traza

**Crear:** `frontend/api/client.js`, `frontend/components/DrawingViewer.js`, `PartsTable.js`, `TracePanel.js`, `ReviewPanel.js`; `frontend/tests/traceability.test.js`, `review.test.js`; configuración mínima de scripts de prueba.

**Interfaces:** consumir GET ledger/drawing, Result y mapa de procedencia de `DrawingPreview`; mantener selección por IDs, no por índice de fila. No duplicar cálculo de medidas en JavaScript.

- [ ] Escribir hover de la balda de tres vistas→resaltar sus tres contornos y ninguna otra instancia; selección inversa vuelve a la fila.
- [ ] Escribir stream 1,2,2,3→tres eventos visibles ordenados; reconexión no duplica actividad.
- [ ] Escribir revisión con versión obsoleta→mensaje y recarga, sin sobrescritura; dimensión ausente se ve como desconocida. Con unidades no resueltas, el dibujo usa coordenadas fuente y no muestra medidas en mm inventadas.
- [ ] Implementar interfaz y estados cargando/parcial/error, con modo visible y etiquetas propuestas diferenciadas.
- [ ] Ejecutar `npm test`; integración en navegador contra backend real de desarrollo, no solo mock; commit.

**Aceptación:** traza de acciones y evidencias, sin razonamiento interno; un usuario puede localizar el origen de una medida.

## T9 — Exportación y cajas esquemáticas

**Crear:** `backend/app/salida/service.py`, `backend/tests/unit/test_exports.py`, `frontend/components/SchematicViewer.js`, `frontend/tests/schematic.test.js`.

**Interfaces:** `export_result(result: Result, format: str) -> ExportArtifact`; formatos P0 `json|csv`. Las cajas consumen exclusivamente `dimensions_mm` verificadas y cantidad revisada. Si no existe despiece, la lectura de cotas sigue accesible en el plano; no inventar filas para un CSV vacío.

- [ ] Escribir exportación con IDs y nulos preservados; textos CSV que empiezan por `=,+,-,@` o control de hoja se protegen sin cambiar JSON original.
- [ ] Escribir 600×400×null→sin sólido completo; 600×400×18 verificado→caja de esas proporciones, rotulada esquemática.
- [ ] Observar fallos; implementar exportadores desde resultado persistido y presentación con transformaciones separadas de la fuente.
- [ ] Comparar tabla, JSON, CSV y visualización para la misma revisión; ejecutar tests y commit.

**Aceptación:** no existe una segunda ruta de cálculo que produzca cifras distintas; PDF queda como extensión.

## T10 — Aceptación y demo del hito técnico

**Crear:** `backend/tests/e2e/test_pipeline.py`, `frontend/tests/e2e/vexplorer.spec.js`; registro de resultados con versiones, corpus/subconjunto y limitaciones. D coordina; todo el equipo revisa.

- [ ] Ensayar un DXF Orla para extracción y un positivo propio de paneles para despiece, rotulados según su procedencia. No anunciar el primero como conjunto reconstruido. Bench Vise sirve de referencia para el piloto PDF P1, no de ejecución DXF.
- [ ] Ejecutar caso incompleto, conflicto, fallo del proveedor y replay; distinguir fallos técnicos y falta de evidencia.
- [ ] Ejecutar desde `backend/`: `python -m pytest`; desde `frontend/`: `npm test` y `npm run test:e2e`. Adjuntar resultados observados, no solo comandos.
- [ ] Probar el recorrido con una persona que no lo implementó; registrar correcciones necesarias y tiempo, sin anunciar ahorro sin comparación.
- [ ] Grabar el guion de [DEMO_Y_OPERACION](docs/DEMO_Y_OPERACION.md), revisar README del producto y defectos abiertos.
- [ ] Congelar cambios funcionales antes de presentar; integrar únicamente correcciones de riesgos observados.

**Cierre:** distinguir explícitamente lo implementado, lo probado y lo pendiente. Publicación, repositorio externo y envío corresponden a acciones posteriores del equipo; este plan no las ejecuta.

## T11 — Corpus de mobiliario e inferencia desde planos pobres

**Rutas futuras:** `backend/app/agente/descomposicion.py`, `backend/tests/evaluation/test_sparse_furniture.py`; ampliar contratos, revisión y frontend tras acuerdo A/B y aviso C. Seleccionar datos desde el inicio para no descubrir al final que falta el caso de negocio.

- [ ] Preparar pares entrada pobre/referencia completa de mobiliario; anotar piezas, secciones, cantidades, medidas y campos desconocidos con segunda revisión.
- [ ] Crear variantes empobrecidas y auditar fugas en capas, bloques, textos, metadatos, archivos vecinos y herramientas; separar familias antes de generar variantes.
- [ ] Acordar un modelo de escenarios de descomposición separado de las piezas confirmadas. Registrar regiones/vistas que motivan cada propuesta aunque no haya contorno individual de la pieza.
- [ ] Probar dos descomposiciones plausibles, componente oculto, espesor ausente y cantidad ambigua; ninguna hipótesis pasa a medida observada ni se suma con alternativas incompatibles.
- [ ] Implementar revisión que acepte/rechace/divida/una propuestas y registre nuevas premisas humanas; regenerar evidencias y fingerprint cuando corresponda.
- [ ] Exportar hechos, cálculos, hipótesis y confirmaciones humanas por separado. Mantener R-015 fuera de alcance hasta acordar sus premisas; registrar escenarios no equivale a habilitar esa regla.

**Aceptación:** un plano empobrecido produce propuestas útiles comparadas con referencia oculta, incluyendo incertidumbre y correcciones. Un fixture sintético permite validar el mecanismo; la utilidad real requiere mobiliario real. No afirmar que el corpus mecánico satisface este criterio.

## T12 — Recuperación histórica y estimación de costes/tiempos

**Rutas futuras:** `backend/app/historico/`, `backend/app/estimacion/`, `backend/tests/evaluation/test_historical_retrieval.py`, `backend/tests/unit/test_estimates.py`. B coordina con A los atributos y C la presentación; sin reservas personales implícitas.

- [ ] Preparar catálogo con dimensiones, materiales, acabados, procedencia, coste/horas disponibles y distinción entre presupuesto y ejecución real; mantener desconocidos y rotular datos sintéticos.
- [ ] Implementar baseline de filtros/distancias y compararla con embeddings versionados. Excluir el propio proyecto, revisiones y duplicados del caso evaluado del índice.
- [ ] Presentar comparables ordenados con diferencias verificables por dimensión, material y acabado; evaluar relevancia con técnico.
- [ ] Calcular estimación por conceptos con cantidades, consumos y tarifas trazables; separar costes fijos, variables y horas. No aplicar un factor dimensional global sin justificación.
- [ ] Probar unidades y monedas incompatibles, falta de tarifas, falta de comparables, doble contabilización y cambio de revisión. Mantener resultado parcial o abstención sin inventar precios.
- [ ] Integrar ficha de compras con despiece revisado, hipótesis, comparables, ajustes, coste, horas, exclusiones y pendientes. El presupuesto conserva la revisión exacta del despiece y catálogo utilizado.

**Aceptación:** cálculos reproducibles con oráculo independiente y selección explicada. Histórico sintético prueba el flujo, pero no acredita precisión económica real.

## T13 — Evaluación y demo de negocio

Seguir [COMPARATIVA_METODOS](docs/COMPARATIVA_METODOS.md) para comparar reglas, modelo visual, modelo con herramientas y herramientas con histórico. La [selección de datasets](docs/INVESTIGACION_Y_DATASETS.md) distingue candidatos de mobiliario, corpus técnico y acceso pendiente.

- [ ] Congelar familias reservadas, referencias, histórico permitido, tolerancias y criterios antes de ejecutar; seguir [CASO_DE_USO_Y_EVALUACION](docs/CASO_DE_USO_Y_EVALUACION.md).
- [ ] Comparar geometría/reglas, harness y revisión humana con la misma entrada pobre. Medir componentes, cantidades, dimensiones, abstenciones y tiempo de corrección.
- [ ] Comparar recuperación por atributos y embeddings; medir coste y horas solo donde exista referencia real y compatible.
- [ ] Mostrar entrada pobre, alternativas, revisión, comparables y estimación explicada; revelar referencia de despiece después de congelar la salida.
- [ ] Publicar tamaño real de muestra, procedencia, sintéticos, errores y capacidades pendientes. No presentar T10 como validación suficiente de negocio.

**Aceptación:** una persona del dominio puede revisar la ficha para compras/administración y rastrear datos y supuestos. El informe contrasta con lectura manual; no promete ahorro o exactitud sin medición. Si faltan referencias reales, registrar ese bloqueo de validación sin inventar resultados.

## P1 — Integraciones que requieren un acuerdo adicional

1. **PDF de conjunto y detalles.** Empezar con Bench Vise y Jaw Pad. Acordar localizadores por página/región, asociación de referencias BOM y dimensiones nominales; no fabricar contornos DXF para completar trazabilidad. Aceptación inicial: 12 referencias, 22 unidades, enlace de Jaw Pad a su detalle y 69,85 × 44,45 × 5 mm con cantidad 2. Las medidas de las otras piezas permanecen sin revisar.
2. **Cadenas dimensionales.** Definir miembros, orientación, marco, signos y premisas. Solo después implementar el ejemplo 18+564+18=600 y su negativo 18+560+18=596.
3. **DWG.** Ejecutar ODA real sobre un par conocido, registrar versión y comparar geometría, unidades y advertencias. Abrir una cabecera no verifica conversión.
4. **Más semántica o geometría mecánica.** Ángulos, radios, tolerancias, materiales y operaciones de mecanizado necesitan modelos y oráculos propios; no extender `thickness` para representar cualquier tercer valor.

La selección P0/P1 y las razones están en [ADAPTACION_DATASET](docs/ADAPTACION_DATASET.md). El equipo puede cambiar la prioridad con una decisión explícita; este plan no presupone que PDF ya esté implementado o que A/B hayan aprobado nuevos campos.
