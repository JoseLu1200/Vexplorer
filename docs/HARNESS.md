# Harness nativo y entrega verificable

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

Estado: especificación propuesta para implementar; este documento no contiene una aplicación ejecutada ni resultados de pruebas de producto. El alcance DXF y los límites geométricos están en [ARQUITECTURA.md](ARQUITECTURA.md). [CONTRATOS_DATOS.md](CONTRATOS_DATOS.md) describe las propuestas de dominio `0.1.0`; las reglas deterministas están en [VALIDACION.md](VALIDACION.md). Al implementar, los modelos Pydantic serán la única fuente de verdad de los contratos JSON; los esquemas de herramientas se generarán desde esos modelos. Los detalles de campos de este documento requieren acuerdo de A/B y aviso a C antes de congelarse; no constituyen un esquema paralelo.

## Responsabilidad y máquina de estados

El harness interpreta un ledger geométrico ya extraído. Puede proponer etiquetas, escoger hipótesis de asociación ya generadas y seleccionar referencias existentes. Una asociación nueva requiere revisión y regeneración del libro; las herramientas no alteran la identidad congelada. No mide mediante texto libre, modifica coordenadas ni sustituye valores del ledger. Una observación dibujada no es una pieza física: tres vistas pueden respaldar un único candidato. La cantidad depende de candidatos físicos confirmados, nunca del número de contornos o proyecciones.

El corpus mecánico auxiliar es `engineering-drawings-harness.zip`, cuya auditoría se recoge en [DATASET.md](DATASET.md). [PlankAssembly](PLANKASSEMBLY.md) está descargado para preparar referencias de mobiliario; sus vistas 2D siguen pendientes. La presencia de DXF, DWG, STEP, PDF o JSON en el archivo no amplía por sí sola el alcance DXF 2D de P0 ni demuestra evidencia de despiece. El catálogo CADBLOCK se descartó como datos de despiece. Tener dibujos disponibles no equivale a haber ejecutado la aplicación propuesta; el soporte de PDF o reconstrucción 3D completa requiere otra decisión.

El prompt y el validador deben distinguir `entity_level=object|part|unknown`. El contorno de un objeto completo puede respaldar su nombre, pero no demuestra componentes o espesores manufacturables. Solo candidatos `entity_level=part` pueden aparecer en `pieces`; los `object` o `unknown` se conservan mediante disposiciones `needs_review` y hallazgos de lectura con evidencia. Su `role` sigue `unknown`; no se generan componentes por apariencia. `entity_level` viaja en candidatas, propuestas y piezas resueltas según los modelos Pydantic acordados. Una altura general de objeto nunca se asigna a `dimension_refs.thickness`.

La secuencia normal es `queued → ingesting → extracting → reasoning → validating`. Una validación reparable puede regresar a `reasoning`. Los estados terminales son `completed`, `needs_review`, `failed`, `cancelled` y `timed_out`; `validating` es transitorio. No se reabre una ejecución terminal. Una revisión produce otra revisión de resultado según [API_Y_EVENTOS.md](API_Y_EVENTOS.md).

`completed` exige al menos una pieza válida, cobertura completa y controles automáticos aplicables sin incógnitas obligatorias. Las etiquetas semánticas con `label_status=proposed` conservan esa condición. Unidades, identidad o dimensiones desconocidas llevan a `needs_review`, con valores ausentes explícitos. Cero candidatas respaldadas también requiere revisión, nunca una finalización completa por ausencia de errores. `failed` corresponde a imposibilidad técnica, ledger inválido o protocolo irrecuperable, no a falta de espesor. `geometry_only` omite el proveedor y normalmente termina mediante la abstención persistida descrita abajo. `recorded_replay` reproduce material guardado, con procedencia visible, sin simular actividad en vivo.

## Adaptador inicial: Claude, sin framework de agentes

El futuro módulo `backend/app/agente/` separará transporte del proveedor y política de ejecución. No se requiere LangChain. MCP queda en P2. El adaptador inicial usará herramientas de cliente nativas de Claude: publicará `name`, descripción e `input_schema`, reconocerá bloques `tool_use` y devolverá `tool_result` correlacionados mediante `tool_use_id`. El servidor ejecuta cada función; una llamada del modelo no concede permisos. Véase el [ciclo oficial de llamadas](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls).

El identificador del modelo, los parámetros admitidos y los tiempos de petición serán configuración de despliegue. No se fija aquí una versión ni un precio. Se conservarán modelo efectivamente utilizado, revisión del adaptador y consumo comunicado por el proveedor, sin inventar métricas faltantes. La interfaz interna propuesta recibe mensajes, definiciones de herramientas y plazo restante; devuelve llamadas normalizadas, motivo de parada y uso. No expone objetos del SDK al dominio. Los esquemas nativos se generarán desde los modelos Pydantic canónicos y se adaptarán al subconjunto admitido por el proveedor. El backend siempre vuelve a validar el objeto completo con esos modelos y las reglas deterministas.

Una respuesta textual ordinaria nunca constituye el despiece final. El proveedor debe solicitar `entregar_despiece`. Si termina sin hacerlo, el harness puede emitir un recordatorio dentro del presupuesto; repetir el incumplimiento termina con diagnóstico, sin extraer números de la prosa. Las llamadas desconocidas o argumentos inválidos reciben error tipado. Un truncamiento no autoriza ejecutar JSON parcial.

## Contratos de herramientas

Las seis herramientas son una lista cerrada. Se rechazan propiedades adicionales, referencias inexistentes y revisiones obsoletas. El contexto autenticado fija `run_id`, documento y propietario; el modelo no proporciona un ámbito alternativo. Cada llamada registrada tiene `tool_call_id`, nombre, hash de argumentos, duración y resultado. El servidor comprueba pertenencia de cada identificador al ledger autorizado.

La notación siguiente propone entradas y salidas para el acuerdo A/B, con aviso a C. `candidate_revision`, `PartCandidate`, `Evidence`, `Measurement`, `Submission` y `ValidationReport` remiten a los futuros modelos Pydantic canónicos; los identificadores son cadenas. Las listas de identificadores son únicas y no vacías salvo indicación contraria.

| Herramienta | Objeto de entrada | `data` de éxito |
|---|---|---|
| `inspeccionar_candidata` | `{candidate_revision, candidate_id}` | `{candidate, observations, measurements, evidence_ids}`: candidato completo, observaciones y medidas referenciadas, sin reinterpretarlas. |
| `obtener_evidencias` | `{candidate_revision, evidence_ids}` | `{evidence, source_entities, measurements}`: evidencia pedida y registros vinculados autorizados. |
| `comparar_candidatas` | `{candidate_revision, candidate_ids}`; exactamente dos candidatos distintos | `{candidate_ids, relations, evidence_ids, unresolved_fields}`. |
| `visualizar_vista` | `{candidate_revision, view_id, highlight_contour_ids}`; resaltados puede ser `[]` | `{artifact_id, view_id, highlight_contour_ids, source_entity_ids, render_config_hash}`. |
| `validar_borrador` | `Submission` completo, sin envoltorio adicional | `ValidationReport` canónico; diagnóstico sin persistir resultado final. |
| `entregar_despiece` | El mismo `Submission` | `{accepted, result_revision, state, validation_report}`. |

Todas las salidas usan `{schema_version,candidate_revision,ok,data,error}`. En éxito, `ok=true` y `error=null`; en fallo, `ok=false`, `data=null` y `error={code,message,details,retryable}`. `schema_version` vale `0.1.0`. `details` es un objeto de diagnóstico sin secretos. Códigos previstos: `invalid_arguments`, `unknown_reference`, `stale_revision`, `scope_denied`, `budget_exhausted`, `deadline_exceeded`, `cancelled`, `validation_rejected`, `already_finalized` y `tool_failure`.

`comparar_candidatas.relations` contiene objetos `{kind,status,evidence_ids}`; `kind` pertenece a `same_physical_part`, `same_dimensions`, `mirrored_variant`, `alternative_hypothesis`; `status` usa `pass|fail|unknown|not_applicable`. `unresolved_fields` es una lista de nombres de campos pendientes. La similitud sugiere una relación, no demuestra intercambiabilidad. `visualizar_vista` solo genera una representación autorizada del ledger, sin cargar URL aportadas por el modelo; el artefacto se resuelve dentro del mismo ámbito mediante el repositorio.

`validar_borrador` puede devolver `ok=true` con un informe que contenga fallos: ejecutar el validador correctamente es distinto de aprobar el despiece. `entregar_despiece` ejecuta ese mismo validador antes de persistir. Con errores de contrato corregibles devuelve `validation_rejected`. Una propuesta válida que conserva incógnitas puede aceptarse con `accepted=true` y `state=needs_review`; un informe `fail/error` impide aceptar ese borrador. La aceptación persiste resultado e informe antes de terminar; las salidas técnicas, cancelaciones y plazos conservan sus estados propios. No se completan espesores ausentes ni se convierten etiquetas propuestas en confirmadas. `confirmed` exige evidencia de origen aceptada o revisión humana autorizada; el LLM no puede autoconfirmar su interpretación.

El backend construye `dimensions_mm` desde referencias validadas, deriva cantidades y exige cobertura de todos los candidatos mediante piezas o disposiciones. Las hipótesis alternativas no son aditivas. Una incompatibilidad entre anotación y geometría sigue siendo conflicto. Ninguna herramienta admite shell, red arbitraria, fórmulas ejecutables ni escritura de medidas. Las cajas 3D solo se habilitan para piezas con tres dimensiones respaldadas y unidades resueltas; una dimensión ausente mantiene la lectura 2D y la revisión, sin rellenar altura o espesor para dibujar volumen.

En P0, las hipótesis alternativas compiten únicamente como interpretaciones de una misma ocurrencia. Una alternativa de una ocurrencia frente a varias requiere revisión y regeneración del libro; no se representa mediante exclusión de candidatos que deberían seleccionarse juntos. Las cadenas dimensionales generales de `R-015` quedan en P1: en P0 se informa `not_applicable` hasta acordar entre A/B una representación estructurada de sus premisas, con aviso a C.

## Abstención del servidor y revisión disponible

Con un ledger íntegro y sin una entrega aceptable, la falta de evidencia o el agotamiento de llamadas/reparaciones producen una propuesta de abstención construida por el servidor: `pieces=[]` y una disposición `needs_review` por cada candidata, con su ID y evidencia existente. Cubre candidatas `part`, `object` y `unknown`, sin cambiar su nivel ni asignar medidas o cantidades. La ambigüedad de identidad no obliga a crear una pieza: si se conserva una propuesta parcial válida, su cantidad será `null`; la abstención total no contiene filas de piezas. El borrador inválido del modelo se conserva separado como diagnóstico y no se publica como resultado resuelto.

Esta propuesta pasa el mismo validador y resolvedor que `entregar_despiece`; se persisten propuesta, informe, resultado revisión 1 y evento terminal en una transacción. `geometry_only` utiliza esta ruta cuando no genera una propuesta determinista respaldada. Si no hay candidatas, ambas listas quedan vacías y una comprobación explícita de cobertura devuelve `unknown/review`, con causa propuesta `no_supported_part_candidates`; el resultado sigue siendo `needs_review`. Así existe un resultado revisable incluso sin intervención del proveedor. El identificador definitivo de esa comprobación se acuerda en los modelos y reglas, sin introducir campos ad hoc.

La integridad del ledger se valida antes de invocar al agente. IDs duplicados, referencias rotas o candidatas sin evidencia válida producen `failed` con causa propuesta `invalid_evidence_ledger`, conservando diagnósticos. La abstención no inventa evidencia para reparar un ledger inválido. Cancelación y plazo vencido conservan `cancelled` y `timed_out`; la persistencia de abstención no permite ganar a un estado terminal ya confirmado ni iniciar trabajo fuera del plazo.

Una revisión humana autorizada usa el resultado existente y crea otra revisión de Result con el mismo ledger. `Run.state` y su historial terminal permanecen inmutables; la interfaz muestra `result.state` para el resultado vigente. Cambiar unidades, fuente o asociaciones congeladas exige otra ejecución y revisión de candidatas.

## Bucle correctivo con límites

Valores iniciales configurables, sin promesa de rendimiento:

| Campo | Valor | Contabilidad |
|---|---:|---|
| `max_model_calls` | 15 | Cada intento enviado al proveedor, incluidos reintentos fallidos. |
| `max_tool_calls` | 30 | Cada llamada solicitada admitida para procesamiento, también inválida o fallida. |
| `max_validation_repairs` | 2 | Cada retorno al modelo para corregir un borrador rechazado; validar y entregar no reinician el contador. |
| `run_timeout_s` | 120 | Fase agente completa, con espera, herramientas y reintentos. |
| `ingest_timeout_s` | 60 | Ingesta separada. |
| `oda_timeout_s` | 30 | Incluido en ingesta, no añadido a sus 60 segundos. |

Se comprueba el presupuesto antes de reservar cada operación; se cuenta al reservar, sin descuentos por errores. Un lote que excedería el saldo se rechaza antes de ejecutarse. Validaciones internas de la entrega no duplican `max_tool_calls`; sí tienen plazo y traza. Agotar llamadas o reparaciones deja `needs_review` con la causa. Vencer el plazo produce `timed_out`. El reloj monotónico gobierna plazos; UTC se usa para auditoría.

Pseudocódigo conceptual, no ejecutado:

```text
fijar ledger inmutable, ámbito y deadline monotónico
mientras ejecución no terminal:
    comprobar cancelación, deadline y presupuestos
    reservar intento de modelo; solicitar respuesta nativa
    comprobar cancelación y deadline otra vez
    normalizar y validar llamadas completas
    si no hay llamadas: registrar incumplimiento y continuar acotadamente
    reservar presupuesto del lote; ejecutar herramientas autorizadas
    si una entrega fue aceptada: terminar con resultado persistido
    si falta evidencia: validar y persistir abstención del servidor; terminar needs_review
    si el error es reparable y queda presupuesto de reparación:
        devolver informe concreto y referencias permitidas
    si se agotaron llamadas o reparaciones: validar y persistir abstención; terminar needs_review
    en otro caso: terminar con diagnóstico y estado técnico correspondiente
```

Un ID mal escrito es reparable consultando registros existentes. Un espesor sin evidencia no mejora repitiendo preguntas al modelo: detener y pedir revisión. Tampoco se reintenta hasta convertir un objeto completo en piezas supuestas. El mensaje de corrección debe pedir abstención explícita si la evidencia solo respalda el objeto, sin inventar su construcción interna. Reintentos de transporte se limitan al saldo y al plazo, con espera acotada y respeto de la señal de cancelación. No hay reintentos automáticos ilimitados de errores de esquema, permisos o evidencia inexistente.

## Exclusión, trazabilidad y confianza

Solo un ejecutor puede reclamar un run mediante actualización transaccional. En P0 se procesan herramientas secuencialmente para simplificar el orden de eventos; futuros paralelismos de lectura deberán reservar presupuesto atómicamente. Entregar y cancelar compiten bajo bloqueo transaccional: gana el primer estado terminal confirmado. La aceptación guarda resultado, informe y evento juntos. Repetir idéntica entrega devuelve la revisión existente; una diferente recibe `already_finalized`. Se conserva hash canónico de Submission, no se usa el ID del proveedor como única clave.

La cancelación interrumpe operaciones cooperativas; una respuesta tardía no modifica un run terminal. Cada llamada bloqueante tiene tiempo máximo menor o igual al saldo global. Desconectar SSE no cancela el trabajo. Al reiniciar el proceso se marcan como `failed` los trabajos interrumpidos, con causa `worker_interrupted`; un nuevo intento requiere nuevo run.

El CAD, incluidos TEXT/MTEXT y nombres de capa, es contenido no confiable. Se delimita como datos, se limita su tamaño y no puede cambiar herramientas o instrucciones. Los permisos y la validación viven en servidor. La interfaz muestra acciones, evidencias, incidencias y resúmenes breves del resultado; no transmite cadena de pensamiento, prompts privados ni mensajes internos completos.

La caché debe incluir hashes original/normalizado y manifiesto de conversión, configuración geométrica y unidades confirmadas, versión de esquema, pipeline, prompt y modelo. Cambiar cualquiera invalida la entrada. Las lecturas cacheadas se señalan en la traza y mantienen procedencia. Un replay muestra run y fecha originales; no reutiliza una aprobación humana en otro documento. El plan de comprobación está en [TEST_PLAN.md](TEST_PLAN.md); aquí no se afirma que esas pruebas se hayan ejecutado.

## Límite de la corrección de identidad en P0

`RunConfig` y el endpoint de revisión propuestos no incorporan nuevas asociaciones físicas ni confirmaciones de ocurrencias de conjunto. La UI P0 permite escoger referencias, etiquetas y alternativas ya sustentadas; si la corrección necesita nueva evidencia de identidad, conserva `needs_review`. Repetir entrada y configuración sin cambios no resuelve esa incertidumbre en un motor determinista. El mecanismo autenticado para introducir tal evidencia, regenerar el ledger e incluirla en el fingerprint queda pendiente de acuerdo A/B y aviso C. Los cambios de unidades y etiquetas de vista sí siguen las entradas propuestas; no se equiparan a confirmar asociación física.

## Herramientas necesarias para la prueba de concepto de negocio

Las seis herramientas del hito técnico no cubren T11–T12. Acordar herramientas adicionales para proponer escenarios de despiece/secciones, recuperar proyectos históricos, inspeccionar sus diferencias y calcular estimaciones con premisas autorizadas. El agente debe poder presentar varias construcciones plausibles y solicitar la decisión del técnico, aunque el dibujo no contenga cada pieza aislada.

Mantener el mismo bucle nativo y presupuestos. El backend calcula dimensiones derivadas y costes; el modelo no inserta valores hipotéticos en el ledger ni altera tarifas. Solo se consulta el índice permitido del histórico, sin acceso a la referencia reservada del caso evaluado. Caché y traza incluyen versión del índice, reglas de cálculo y escenario. Una alternativa sin validación sigue siendo propuesta, incluso si permite mostrar un presupuesto provisional.

## Aislamiento para el futuro piloto de mobiliario

El harness que compare métodos con [PlankAssembly](PLANKASSEMBLY.md) recibirá solo las vistas permitidas de un caso. Sus herramientas no podrán abrir `data.zip`, `model/*.json`, respuestas del evaluador ni variantes completas del mismo mueble. Limitar permisos y rutas; separar carpetas por sí solo no basta. No introducir referencias reservadas en prompts, trazas o el índice de comparables.

La pista con histórico requiere un catálogo admitido y libre de duplicados del caso. Sin histórico económico, solo puede evaluarse recuperación geométrica, no precisión de presupuesto. Esta preparación e inferencia están pendientes; el preparador mecánico existente no ejecuta el harness.
