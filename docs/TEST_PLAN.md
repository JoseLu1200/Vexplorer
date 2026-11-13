# Plan de pruebas y evaluación

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

**Estado: casos propuestos, ninguna prueba de producto ejecutada.** [DATASET.md](DATASET.md) registra la auditoría del nuevo corpus: 14 componentes CAD Orla y 51 conjuntos PDF. No se reutilizan las particiones del descartado Cadblock. La propuesta contractual `0.1.0` requiere acuerdo A/B y aviso a C; los modelos Pydantic serán su única autoridad futura, incluidos esquemas de herramientas. Véanse [CONTRATOS_DATOS.md](CONTRATOS_DATOS.md), [HARNESS.md](HARNESS.md) y [API_Y_EVENTOS.md](API_Y_EVENTOS.md).

## Material y oráculos

P0 usará DXF Orla para extracción admitida y fixtures propios para comportamiento de paneles rectangulares. Crear seis familias controladas: panel métrico; equivalente en pulgadas; tres vistas de una balda; bloques uniformes; cota con texto sobrescrito; variantes especulares dibujadas explícitamente. Añadir unidades desconocidas, entidades no soportadas y casos incompletos. Escribir las coordenadas, medidas esperadas y ocurrencias físicas fuera del sistema probado y someterlas a segunda revisión.

Separar extracción CAD, lectura de BOM y despiece de conjuntos. En Orla, los JSON de cotas y mediciones son referencias del publicador, no etiquetas semánticas certificadas; si son oráculo, el agente no los recibe. Bench Vise aporta BOM revisada y solo un conjunto dimensional revisado. Julius tiene planos con evidencia de BOM, pero no JSON completo validado por pieza. PDF es piloto P1, pendiente de acuerdo A/B y soporte de página/región; no una entrada P0 existente.

La partición se congelará por assembly/componente y familia después de admisión manual; agrupar formatos, páginas, vistas, variantes y revisiones. Las muestras ya inspeccionadas quedan en desarrollo/demo. No se fijan tamaños train/dev/test antes de contar casos elegibles. La pista ciega oculta nombres/títulos externos; conserva texto legítimo del dibujo. Publicar denominadores y cobertura por tarea.

## P0: geometría, unidades e identidad

| ID | Entrada | Resultado esperado |
|---|---|---|
| GEO-01 | Rectángulo propio `(0,0),(600,0),(600,400),(0,400)`, mm | Extensiones `600` y `400` mm, procedencia completa; sin espesor inventado. |
| GEO-02 | Segmento `(0,0)`–`(1,0)`, pulgadas | `25.4` mm y coordenada fuente `1` conservada. |
| GEO-03 | GEO-01 sin unidad | `needs_review`; preview en `source`, sin normalización implícita. Confirmar mm exige nueva ejecución/fingerprint. |
| GEO-04 | Longitud geométrica `600`, cota textual «620» | Conservar `600` y `620`, estado `conflict`; no elegir silenciosamente. |
| GEO-05 | Modelo `600 × 400`, paperspace `1:10` | Medidas de modelo `600`/`400`, no `60`/`40`; paperspace fuera de P0, sin otra ocurrencia. |
| GEO-06 | Segmento local `(0,0)`–`(100,0)`, INSERT escala `2`, giro `90°`, origen `(10,20)` | Extremos `(10,20)` y `(10,220)`, longitud `200`; instancias con `insert_path` distinto aunque compartan handle. |
| GEO-07 | INSERT no uniforme/reflejado o spline no soportada | Cobertura y limitación explícitas; ninguna entidad desaparece silenciosamente. |
| ID-01 | Vistas `600 × 400`, `18 × 400`, `600 × 18`, asociación respaldada | Tres observaciones, un candidato confirmado, dimensiones `600/400/18`, cantidad `1`. |
| ID-02 | Mismas vistas sin asociación suficiente | Identidad ambigua, `needs_review`; abstención puede usar `pieces=[]`. Si hay pieza parcial válida, cantidad `null`, nunca `3`. |
| ID-03 | Dos paneles físicos confirmados e intercambiables `600 × 400 × 18` | Dos candidatos cubiertos una vez; cantidad agrupada `2`. |
| ID-04 | Paneles iguales en envolvente, taladro `x=30` frente a `x=570`, orientación conocida | Variantes separadas, cantidad `1` cada una; semejanza no prueba intercambiabilidad. |
| ID-05 | Una vista `600 × 400`, sin espesor | `thickness=null`, `needs_review`, sin caja 3D completa. |
| ID-06 | Candidata `entity_level=object|unknown` con altura general | Disposición `needs_review`; cero componentes inventados y ninguna altura convertida en espesor. |

## P0: regresiones del corpus Orla

| ID | Entrada real y referencia de auditoría | Comportamiento futuro esperado |
|---|---|---|
| COR-01 | Los 14 DXF: tres `$INSUNITS=4`, once `0` | Resolver mm solo donde esté respaldado; once casos conservan unidad desconocida salvo confirmación explícita. No heredar mm del STEP sin autorización. |
| COR-02 | Sidecars: 419 registros, 370 `dimension` y 49 `dimension_style` | Importador distingue estilos de cotas. Entre las cotas, preservar 356 `drawing_unit` y 14 `degree`; ninguna angular se publica como longitud mm. |
| COR-03 | Cuatro `ARC_DIMENSION` fuera del JSON: `FEE/FF3` en `drawing_87852…`, `4FD/50C` en `drawing_bcb355…` | Extracción real las conserva si están soportadas o señala limitación; comparar solo con JSON no permite declarar cobertura total. |
| COR-04 | 50 cotas con `text_override` no vacío | Preservar valor bruto, texto, estilo y procedencia; no sustituirlos por un único valor supuestamente equivalente. |
| COR-05 | `drawing_1b796…`, handle `5319`: calculado ≈`67.00000000006793`, bruto `44.66666666671191`, factor `2/3`, texto `45` | Los cuatro datos permanecen distinguibles; no multiplicar otra vez el bruto ni afirmar equivalencia automática. Oráculo nominal requiere revisar estilo/marco. |

Estos casos comprueban conservación e interpretación limitada, no 14 despieces correctos. El cotejo DXF/JSON ya auditado no es una suite de Vexplorer ejecutada. Medir precisión dimensional solo sobre campos con referencia independiente admitida.

## P0: validación, abstención y herramientas

`ValidationCheck.result` usa `pass|fail|unknown|not_applicable`; `ValidationReport.outcome`, `pass|needs_review|fail`. Un error con `fail` rechaza el borrador; una revisión con incógnitas no equivale a aprobación. Los IDs de esta tabla son tests; `R-xxx` identifica la regla propuesta correspondiente.

| ID | Entrada o acción | Resultado esperado |
|---|---|---|
| VAL-03 | Medidas exteriores e interiores sin cadena estructurada | `R-015=not_applicable` siempre en P0; no sumar largos arbitrarios. |
| VAL-04 | Contornos superpuestos entre vistas | Colisión física `not_applicable`; solape 2D y AABB no prueban colisión. |
| VAL-05 | Dos alternativas de UNA misma ocurrencia | Selección exclusiva y disposición `rejected_alternative` respaldada; nunca suma de alternativas. Una frente a varias exige revisión/regeneración, fuera de esta exclusión P0. |
| VAL-06 | Candidata omitida, duplicada o en pieza y disposición | Rechazo del borrador; cada candidata tiene exactamente un destino. |
| ABS-01 | Ledger íntegro con dos candidatas y evidencia insuficiente | Servidor genera `pieces=[]` y dos disposiciones `needs_review`; validador/resolvedor reales, Result revisión `1`, informe/evento persistidos atómicamente. |
| ABS-02 | Ledger íntegro sin candidatas | `pieces=[]`, `dispositions=[]`, `R-018=unknown/review`, causa `no_supported_part_candidates`, Result revisión `1`, estado `needs_review`; jamás `completed` por vacío. |
| ABS-03 | Ledger con referencias rotas, IDs repetidos o evidencia inválida | `failed`, causa `invalid_evidence_ledger`; sin evidencia inventada ni resultado aceptado fabricado. |
| TOOL-01 | ID `measurement_fake`, número libre o referencia ajena | Rechazo estructural/de ámbito; backend solo resuelve números desde referencias autorizadas. |
| TOOL-02 | `candidate_revision` o `base_result_revision` obsoleta | `stale_revision` de herramienta o `409 stale_result_revision` HTTP; resultado actual intacto. |
| TOOL-03 | `inspeccionar_candidata`, `obtener_evidencias`, `comparar_candidatas`, `visualizar_vista` | Ledger antes/después idéntico; sin escritura de geometría/medidas. |
| TOOL-04 | `validar_borrador` y dos `entregar_despiece` idénticas | Mismo validador; una finalización. Entrega diferente posterior: `already_finalized`. |
| TOOL-05 | LLM intenta `label_status=confirmed` sin autoridad | Rechazo R-014; solo una nueva propuesta `proposed` procede del agente. |

Añadir dimensiones cero/negativas, `NaN`, infinito, duplicados y derivaciones inválidas: dimensión de pieza estrictamente positiva, medición finita no negativa. Las tolerancias no rescatan entradas inválidas. Agotamiento de llamadas con ledger válido usa ABS-01; cancelar o vencer plazo conserva su estado, sin persistencia tardía que lo sustituya.

## P0: ejecución, API e interfaz

| ID | Acción | Resultado esperado |
|---|---|---|
| RUN-01 | Proveedor falso con errores y reparaciones | Máximos `15` intentos, `30` herramientas, `2` reparaciones; todo intento cuenta. Agotar presupuesto persiste abstención `needs_review`. |
| RUN-02 | Reloj supera fase agente `120` s o ingestión `60` s | `timed_out`; ODA limitado a `30` s dentro de ingestión. Sin trabajo tardío fuera del plazo. |
| RUN-03 | Cancelar dos veces y recibir respuesta tardía | `cancelled` estable; ninguna finalización posterior. |
| RUN-04 | Entrega/abstención y cancelación compiten | Gana primera transacción terminal; una revisión final, sin persistencia parcial. |
| RUN-05 | Reinicio con trabajo activo | `failed/worker_interrupted`; nuevo intento explícito, sin reanudación silenciosa. |
| REV-01 | Revisar Result `1` válido en revisión | Crear revisión `2`, preservar `1`; `Run.state` terminal inmutable y UI usa `result.state` vigente. |
| SSE-01 | Historial `1,2,3,4`, reconexión con cursor `2` | Recibir `3,4`; deduplicar por `(run_id,sequence)`; desconectar no cancela. |
| CACHE-01 | Huella exacta repetida y después cambio de unidades/modelo/prompt/esquema/pipeline/conversión | Solo coincidencia completa reutilizable; cambios producen otra clave y procedencia visible. |
| MODE-01 | `geometry_only` y `recorded_replay` | Etiqueta persistente; abstención revisable cuando corresponda. Replay muestra ejecución/fecha originales. |
| UI-01 | GET `/ledger`, `/drawing`, hover de balda ID-01 | Revisiones iguales y mapa estable entidad/evidencia/contorno; tres vistas de la misma fila, cantidad `1`. |
| UI-02 | `pieces=[]` y cota general con unidad desconocida | Preview `source`, aviso de unidad, cota seleccionable vía ledger; ningún `points_mm` o fila de pieza inventada. |
| UI-03 | Artefacto de otro run o ID inexistente | GET `/artifacts/{artifact_id}` devuelve `404`; sin rutas, traversal, scripts SVG o referencias externas. |
| EXP-01 | Nombres `=1+1`, `+SUM(A1:A2)` | CSV seguro propuesto `'=1+1`, `'+SUM(A1:A2)` con IDs estables; JSON conserva texto original. |
| API-01 | Bytes `20971520/20971521`; entidades `100000/100001` | Primer límite no rechazado por tamaño/conteo; segundo rechazado. Probar DXF inválido y formato no admitido. |
| API-02 | Repetir POST con misma `Idempotency-Key`, luego cambiar cuerpo | Mismo recurso con cuerpo idéntico; distinto cuerpo `409 idempotency_conflict`. |

## P1 y criterios de salida

**VAL-01/P1:** cadena estructurada y confirmada, mismo eje/marco: `18+564+18=600`, ancho exterior `600`; esperar `pass`, diferencia `0`. **VAL-02/P1:** vano `560`; suma `596`, diferencia `4` mm, `fail`. Antes se acordarán premisas y representación A/B con aviso a C. Estos casos no habilitan R-015 en P0.

**PDF-01/P1:** Bench Vise, BOM visible de 12 referencias/22 unidades y Jaw Pad cantidad `2`, `69.85 × 44.45 × 5.00 mm`; comparar transcripción oculta con evidencia de página/región. Las otras once referencias conservan dimensiones no revisadas. Respetar DO NOT SCALE DRAWING: no convertir píxeles a cotas nominales. Julius exige anotación humana previa. DWG P1 necesita ODA instalado y verificado; ausente produce `conversion_unavailable` y opción de DXF.

Para presentar P0 se propone ejecutar y superar sus casos con evidencia, navegar de cada medida a la fuente y mostrar incertidumbres. Informar contornos/medidas, asociación, cantidades y abstenciones por separado; `completed` no es exactitud ni aptitud de fabricación. Registrar defectos, tamaño real de muestra y campos sin oráculo. Hoy todos los criterios de producto permanecen pendientes.

## Aceptación adicional de negocio: T11–T13

| Caso | Resultado esperado |
|---|---|
| NEG-01: mueble con entrada empobrecida y despiece reservado | Propuestas contrastables; referencia inaccesible al agente; informar errores y campos desconocidos |
| NEG-02: BOM borrada del visor pero presente en bloque/atributo | Auditoría de fuga rechaza la entrada de evaluación hasta sanearla |
| NEG-03: una pieza frente a tres componentes plausibles | Escenarios separados y revisables; no suma de alternativas ni medidas inventadas |
| NEG-04: técnico divide componente y confirma montaje | Nueva revisión/premisas y fingerprint; conservar resultados anteriores |
| NEG-05: histórico contiene revisión o escalado del caso reservado | Excluir toda la familia/proyecto de la recuperación de evaluación |
| NEG-06: dimensiones similares, material/acabado distintos | Explicar diferencias; no atribuir mismo coste automáticamente |
| NEG-07: coste fijo 40 EUR y material 60 EUR; consumo material por 1,5, demás factores 1 | Fixture sintético: 40 + 60 × 1,5 = 130 EUR; no escalar el fijo. Sin horas de referencia, horas desconocidas |
| NEG-08: falta tarifa, unidades o moneda incompatible | Abstención/parcial y explicación; no número fabricado ni conversión implícita |
| NEG-09: atributos frente a embeddings | Comparar relevancia top-k con anotación independiente y versión del índice |
| NEG-10: evaluación con técnico | Comparar tiempo/correcciones y calidad frente a lectura manual; separar reales/sintéticos |

Estos casos son especificaciones pendientes, no pruebas ejecutadas. Medir los indicadores y admitir varias construcciones plausibles conforme a [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Pasar la suite técnica no basta para afirmar cumplimiento de la transcripción.

## Comparación de reglas, visión, herramientas e histórico

Aplicar [COMPARATIVA_METODOS](COMPARATIVA_METODOS.md): separar representación común de comparación del flujo completo; controlar información, particiones por familia, abstenciones, tiempo humano y recursos. El piloto actual es desarrollo. Histórico y coste quedan no evaluados mientras falten referencias adecuadas.
