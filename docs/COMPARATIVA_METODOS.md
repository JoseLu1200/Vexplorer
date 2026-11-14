# Comparativa de métodos para Vexplorer

Estado: protocolo propuesto, sin ejecuciones de inferencia. Desarrolla la comparación planteada por el usuario y la [revisión de investigación y datasets](INVESTIGACION_Y_DATASETS.md). El [piloto actual](PILOTO_DATASET.md) verifica preparación e integridad, no precisión de modelos.

## Pregunta experimental

Cuánto aportan las herramientas y el histórico a la calidad del despiece y al tiempo de corrección, manteniendo explícita la información disponible. Familia inicial propuesta: armarios/estanterías rectangulares de tableros; los casos mecánicos actuales verifican capacidades técnicas por separado.

| Variante | Información y capacidades | Comparación que permite |
|---|---|---|
| A: reglas | Extracción y reglas deterministas, sin LLM | Referencia técnica para medidas y abstención |
| B: modelo visual directo | Imágenes permitidas, unidades respaldadas y tarea; sin herramientas ni referencias | Capacidad del modelo con una entrada fija |
| C: modelo con herramientas | Mismo modelo e información que B, más herramientas de inspección/cálculo sobre esa entrada | Aporte del bucle de herramientas |
| D: herramientas más histórico | C y un índice permitido de casos anteriores, sin duplicados del caso evaluado | Aporte marginal de recuperación histórica |

Los cuatro métodos están pendientes de implementación/evaluación. D requiere histórico anotado y admisión del índice; si falta, informar «no evaluado», nunca inventar comparables ni una puntuación cero.

## Igualdad de información y diferencias de formato

Separar dos experimentos:

1. **Representación común:** B/C/D reciben exactamente los mismos renders y contexto legítimo; C solo deriva información de esa misma entrada. Si A necesita vector y no existe extractor determinista raster comparable, marcar A como no aplicable en esta pista.
2. **Flujo completo:** mismo documento fuente, con acceso de A/C/D a primitivas DXF y de B al render. Informar esa diferencia: mide la utilidad del sistema completo, no aísla el efecto de las herramientas.

No comparar reglas sobre coordenadas DXF exactas con visión sobre un PDF rasterizado y atribuir toda diferencia a razonamiento. Fijar renders, resolución, selección de vistas, unidades y hashes. Evaluar por separado vistas conocidas/desconocidas y entradas completas/empobrecidas. Ningún método recibe STEP, BOM, programa de forma ni el detalle reservado para puntuar.

## Congelación de datos y ejecución

- Separar por mueble/familia/proyecto antes de generar vistas y variantes; duplicados y revisiones no cruzan particiones ni entran como vecinos del caso de prueba.
- Una ejecución recibe solo su ZIP individual, con contexto nuevo y herramientas restringidas. El ZIP agregado es transporte y contiene variantes relacionadas.
- Registrar versión del modelo, prompt, extractor, índice y reglas; límites de tiempo/llamadas, parámetros y hashes de entrada/salida. Usar los presupuestos de PLAN.md como límites, no como mediciones.
- Comparar C y D con el mismo modelo y límites; registrar gasto real. Si un modelo no admite semillas reproducibles, declarar esa limitación y conservar cada repetición.
- Propuesta inicial: tres repeticiones por método estocástico y caso, sin elegir la mejor a posteriori. Fijar presupuesto concreto antes de lanzar llamadas; esta documentación no las ejecuta.
- Contratos de salida y herramientas siguen pendientes del acuerdo A/B y aviso C exigido por CLAUDE.md; este protocolo no cambia contratos/ ni declara ese acuerdo.

## Qué medir

| Dimensión | Medición y denominador |
|---|---|
| Extracción | Error absoluto por cota y aciertos dentro de tolerancia predefinida, solo en campos con referencia y unidad fiables |
| Identidad/despiece | Componentes propuestos y confirmados, falsos positivos, omisiones y cantidades; correspondencia independiente antes de calcular precisión/recobrado |
| Evidencia | Fracción de afirmaciones respaldadas y referencias correctas; hipótesis explícitas separadas de hechos |
| Abstención | Cobertura en campos resolubles y abstención correcta en los no identificables; penalizar tanto inventar como abstenerse siempre |
| Geometría | Coherencia dimensional y entre vistas, únicamente con premisas verificadas; ejecución de CAD y similitud no sustituyen identidad |
| Recuperación | Recall@k/relevancia sobre vecinos etiquetados, explicaciones de diferencias y tasa de duplicados excluidos |
| Economía | MAE de coste y horas, cobertura y error relativo solo con referencia válida; comparar analogía y modelos tabulares con atributos disponibles en el momento del presupuesto |
| Utilidad humana | Minutos y correcciones hasta ficha aceptable, con orden de métodos contrabalanceado y evaluación independiente de las etiquetas del método |
| Recursos | Tiempo total, llamadas, tokens y coste de ejecución observado, no estimado a partir de una tarifa no comprobada |

No usar una puntuación global para ocultar errores críticos. Cuando no hay una única construcción identificable, aceptar alternativas justificadas y evaluar preguntas pendientes; no penalizar la falta de conocimiento de una pieza oculta como si fuera una cota visible omitida. Publicar tamaños de muestra, campos sin referencia, fallos y resultados por familia.

## Aplicación al piloto existente

- Los 14 DXF son pruebas de extracción de piezas individuales con anotaciones, no 14 problemas de despiece desde un plano pobre.
- visual-001 permite valorar propuestas y reconocimiento de incertidumbre, pero una vista sin cotas no identifica de forma única la BOM completa.
- visual-002 controla lectura de dimensiones; visual-003 exige conservar desconocidos el espesor y la cantidad. Ejecutarlos en contextos separados.
- Todos son casos de desarrollo ya inspeccionados. Para afirmar generalización hacen falta casos reservados que no se hayan usado para ajustar prompts/reglas.
- El histórico económico no está en este piloto. La fase de costes requiere datos adicionales; una prueba con tarifas sintéticas solo valida aritmética.

## Criterio de continuidad

Escoger el método que reduzca trabajo humano manteniendo los errores y la cobertura acordados con el técnico; no el que produzca más piezas ni el render más atractivo. Conservar A como baseline aunque C/D resulten mejores. Integrar un corpus de mobiliario si aporta pares verificables y un campo de evaluación que hoy falta, no simplemente más volumen.

## Preparación de la comparación con PlankAssembly

[PlankAssembly](PLANKASSEMBLY.md) ya está disponible localmente; aún faltan vistas y casos admitidos. Conservar la separación oficial de 24.039/1.329/1.339 como referencia y auditar variantes/duplicados antes de construir una evaluación por familia. Excluir los 985 JSON no listados de comparaciones sobre el split oficial. Marcar como desarrollo los ejemplos inspeccionados.

B/C reciben vistas equivalentes del conjunto, sin programa fuente ni identificación de piezas filtrada por capas. Comparar controles completos y variantes pobres, manteniendo separados sus resultados. La referencia contiene cuboides y asociaciones, no un coste industrial. D puede evaluarse para recuperación geométrica si se prepara un índice independiente y etiquetado; la estimación económica continúa no evaluable sin históricos fiables.

## Implementación

Estado: arnés ejecutable en `evaluation/comparativa/` y `tools/comparativa_metodos.py`; tests en `tests/test_comparativa_metodos.py`. No cambia `contratos/` ni el harness del agente: los componentes de salida son formato propio del arnés. Solo A se ha ejecutado; B/C/D se han probado únicamente con dobles y no se ha realizado ninguna llamada de pago.

### Qué se puede ejecutar ya

```text
python -m tools.comparativa_metodos run --run-dir <dir>                       # A sobre los casos propios de desarrollo
python -m tools.comparativa_metodos freeze --run-dir <dir> --variants A       # fase 1: ejecuta y congela
python -m tools.comparativa_metodos score  --run-dir <dir>                    # fase 2: verifica el sello y abre la referencia
python -m tools.comparativa_metodos run --corpus plankassembly --public-dir <pub> --private-dir <priv> --run-dir <dir>
```

El informe se escribe en `<run-dir>/report.json` y `report.md` (determinista para entradas y reloj iguales; sin rutas absolutas). Las salidas de cada método, `freeze.json` e `inputs/` quedan en el mismo directorio.

- **A (reglas):** dos rutas, declaradas por separado en versiones, informe y cada salida (`versions.run.rule_path`). **A1** (`separated_part_views`): `extract_drawing` + `extract_separated_parts`, sin regla añadida. **A2** (`assembled_orthographic`): `extract_drawing(input_kind="general_furniture")` + `derive_rectangular_hypotheses` agrupadas por tamaño; A2 es una regla adicional del arnés: el análisis `geometry_only` de mueble general de la app solo extrae y no llama a `derive_rectangular_hypotheses`. Registra hashes de `extraction.py` y `parts.py`. Una proyección rectangular nunca fija espesor ni cantidad. Sobre los planos de PlankAssembly los contornos de tableros que se tocan se fusionan en una componente no rectangular y A2 devuelve como mucho una hipótesis por plano: es un resultado, no un fallo del arnés; recuperar los tableros exigiría cambiar `backend/app/geometria/`, fuera de este alcance.
- **B/C/D:** solo con `--enable-model-variants` y `--adapter modulo:fabrica`; el arnés no incluye proveedor. El adaptador recibe un `AdapterRequest` (caso público, repetición, límites, `tools_enabled`, precedentes saneados para D) y devuelve un `AdapterResponse` (componentes, uso real, versiones de modelo/prompt, hashes de artefactos, hash de traza). `describe()` del adaptador se filtra con lista blanca (`name, provider, model, version, prompt_sha256, extractor, parameters, seed_supported`) antes de escribirse. Repeticiones: 3 por defecto para los estocásticos (`--repetitions`), todas conservadas. Límites por defecto 15 llamadas de modelo, 30 de herramientas, 120 s: son topes, no mediciones. Una salida cuyo uso declarado supera las llamadas permitidas se marca `failed:limit_exceeded`; una que excede el tiempo, `failed:timeout_exceeded`. El tiempo no es preventivo: se comprueba al volver el método, así que el adaptador debe imponer su propio corte. Los mensajes de error se guardan sin rutas absolutas (`<path>`).
- **D sin índice admitido:** si falta el índice, no está `admitted`, no está `annotated` o queda vacío tras excluir el mismo caso y la misma partición, cada observación es `not_evaluated` con motivo y el adaptador no se invoca. Nunca se puntúa como cero. La exclusión falla cerrada: cada entrada del índice debe traer `entry_id`, `case_id` y `partition_id` no vacíos (si no, el índice se rechaza), el método solo recibe `partition_id` del caso (no `CaseMeta`), y si falta se lanza error. Al adaptador solo llegan los campos `entry_id, summary, dimensions_mm, components, materials, cost_eur, hours`.
- **Congelación:** cada salida se escribe con creación exclusiva y se hashea; `freeze.json` lista los hashes y su digest. La referencia privada solo se abre a través de `ManifestReader.load_references(token)`, que exige un `FreezeToken` obtenido de `verify_freeze` (vuelve a hashear todo, detecta modificaciones, ficheros añadidos y rutas duplicadas). `score_run` coteja además los hashes de entrada y la descripción del corpus actuales con los del sello antes de abrir la referencia; un caso añadido, cambiado o ausente da un error controlado. Tests con espía comprueban que el fichero privado no se abre sin sello, con una salida alterada ni con entradas cambiadas. La CLI imprime `outputs_digest` al congelar: conviene anotarlo fuera del directorio de la ejecución (también va en el informe).
- **Entrada de los métodos:** solo `PublicCase` (las siete claves del zip individual `agent_cases/<id>.zip`, verificadas contra el hash) y el DXF preparado en `<run-dir>/inputs`. En el corpus de desarrollo los ids son opacos (`dev-001`…) y el DXF se copia fuera de `data/planos_demo`; el mapeo vive en el lector. Un test comprueba que A da las mismas componentes con la ruta original y la preparada (`extraction.py` marca `synthetic` si `planos_demo` está en la ruta, pero eso no afecta a las componentes). `split` y `family_hash` quedan en el lado del arnés (`CaseMeta`).
- **Emparejamiento y métricas:** independientes de la referencia y de las claves (el resultado no cambia al renombrar componentes). Acierto de identidad: todas las cotas conocidas del componente se colocan en dimensiones distintas de la referencia (sin depender de las etiquetas) y toda cota que cae en un campo identificable debe estar dentro de la tolerancia de emparejamiento (5 mm), con al menos dos cotas ajustadas; una cota en un campo no identificable no bloquea el emparejamiento y se puntúa después como invención. Una cota identificable fuera de tolerancia ya no cuenta como cubierta: una predicción 5000×500×20 frente a un tablero 700×500×20 no es un acierto (se publica aparte como `identity.matched_partial`, que no entra en precisión, recall, cobertura ni MAE). Las componentes de referencia de dimensiones idénticas forman una clase; dentro de ella la asignación se resuelve de forma exacta (algoritmo húngaro, cualquier tamaño de clase) y es la más favorable a la predicción (máximo de emparejamientos válidos, menos invenciones, menos campos resolubles sin responder, menor error, más cantidades exactas), sin depender del orden de las claves. Esa cifra es optimista dentro de clases ambiguas (abstenerse en la componente identificable y afirmar la no identificable puntúa perfecto), así que se publican `identity.ambiguous_class_pairs` (emparejamientos resueltos en clases de más de una componente) y `abstention.lower_bound` (la misma abstención con la asignación menos favorable). Solo después se calculan cobertura dimensional, MAE, tolerancia, falsos positivos, omisiones, precisión/recall por tipos, abstención correcta (campos con `identifiable=false`), afirmaciones no identificables, sobre-abstención, tamaños de muestra, casos y campos sin referencia, y recursos (tiempo, llamadas, tokens, coste solo si el adaptador lo observó). Las observaciones `failed` suman sus tipos de referencia y campos resolubles a los denominadores de recall y cobertura (no encontraron nada); se publica además la métrica `*_conditioned_on_ok`. `not_evaluated` y `not_applicable` quedan fuera. La precisión/recall de cantidades cubre solo cantidades identificables (`scope: identifiable_quantities_only`); las no identificables se miden en la abstención. Resultados por variante × familia × partición, sin puntuación global.

### Interfaz del lector de manifiesto

`ManifestReader` (en `evaluation/comparativa/manifest.py`) es la costura para adaptar el corpus: una subclase implementa `public_cases() -> list[PublicCase]`, `case_meta() -> dict[str, CaseMeta]` (familia, partición, `partition_id` para excluir vecinos, desarrollo/reservado), `corpus_info()` y `_read_private() -> dict[case_id, ReferenceCase | None]` (`None` = sin referencia). La compuerta de congelación la hereda de `load_references`. `PlankAssemblyManifestReader` lee hoy la salida de `tools/prepare_plankassembly.py`: `cases.json` + `manifest.json` + `agent_cases/*.zip` (público) y `references.json` con `bounds_mm` (privado); agrupa tableros de igual tamaño en tipos con cantidad. Las cantidades de PlankAssembly se anotan como no identificables desde las vistas (`quantity_identifiable=False`, criterio del proyecto «las vistas no implican cantidad»). `DevelopmentManifestReader(demo_dir, reference_dir, staging_dir)` usa `piezas_*` de `data/planos_demo` con `evaluation/reference/piezas_reference.json` y ids opacos: tres con referencia (completo; cantidad y espesor de K3 no identificables, derivados de los controles), dos sin referencia. Quedan fuera `estanteria_*` (alternativas y campos sin anotar), `mesa_*` (contrato de mesa) y los controles de descriptor.

### Qué falta

- Ejecutar B/C/D reales: un adaptador de proveedor (lo lleva quien mantiene `backend/app/agente/` y `general_furniture/`), presupuesto fijado antes de lanzar y un índice histórico anotado y admitido para D.
- Corpus PlankAssembly mayor y casos reservados no usados para ajustar reglas ni prompts; cuando cambie el formato del manifiesto basta adaptar su lector.
- Un extractor determinista de tableros para vistas ortográficas con contornos que se tocan (A2); sin él A queda cerca de cero cobertura en ese corpus.
- Evidencia/trazabilidad de afirmaciones, geometría entre vistas, recuperación, economía y utilidad humana: no se miden aquí. `evaluation/metrics.py` no se invoca todavía (necesita cabecera de dataset, costes y escenarios que este arnés no produce); sus métricas de recuperación y tiempo humano siguen en `tools/evaluate_cases.py`.
- Repeticiones estocásticas se puntúan agrupadas; falta un resumen de varianza por repetición.
