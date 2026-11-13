# API HTTP, eventos y revisiones

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

Estado: contrato propuesto para implementar con FastAPI; no describe un servicio desplegado ni pruebas ejecutadas. Los objetos de dominio se definen en [CONTRATOS_DATOS.md](CONTRATOS_DATOS.md). El ciclo del agente y sus presupuestos están en [HARNESS.md](HARNESS.md). Todas las rutas siguientes requieren autenticación y autorización sobre el documento/run; conocer un ID no concede acceso.

Los modelos Pydantic serán la única fuente de verdad de los contratos JSON y generarán sus esquemas. Las rutas, campos y sobres siguientes son propuestas documentales para acuerdo A/B, con aviso a C antes de congelarse. No se mantiene un esquema JSON manual en paralelo ni se atribuye a estas tablas una implementación existente.

## Convenciones y endpoints

Prefijo `/api/v1`; JSON UTF-8, `snake_case`, `schema_version="0.1.0"`, fechas UTC ISO 8601. Éxito JSON: `{schema_version,data,meta:{request_id}}`. Error JSON: `{schema_version,error:{code,message,details,retryable},meta:{request_id}}`. Los campos indicados son obligatorios; `details` es un objeto y no incluye rutas internas, secretos ni respuestas completas del proveedor. SSE y archivos descargados tienen su propio formato, descrito abajo.

| Método y ruta exacta | Entrada | Respuesta propuesta |
|---|---|---|
| `POST /api/v1/documents` | `multipart/form-data`, campo `file` | `201`, `data={document_id,original_filename,original_sha256,size_bytes,media_type}`. |
| `POST /api/v1/runs` | `{document_id,mode,run_config,recorded_run_id?}` | `202`, instantánea Run en `data`; cabecera `Location` con ruta GET del run. |
| `GET /api/v1/runs/{run_id}` | Sin cuerpo | `200`, instantánea Run en `data`, incluyendo resultado e informe disponibles. |
| `GET /api/v1/runs/{run_id}/ledger` | Sin cuerpo | `200`, `EvidenceLedger` inmutable autorizado en `data`; `409 ledger_unavailable` mientras no exista. |
| `GET /api/v1/runs/{run_id}/drawing` | Sin cuerpo | `200`, `DrawingPreview` autorizado en `data`; `409 drawing_unavailable` mientras no exista. |
| `GET /api/v1/runs/{run_id}/artifacts/{artifact_id}` | Sin cuerpo | `200`, bytes de un artefacto permitido vinculado al run; formato y tipo de contenido declarados, sin rutas de almacenamiento. |
| `GET /api/v1/runs/{run_id}/events` | `Last-Event-ID` opcional | `200 text/event-stream`, eventos persistidos y nuevos. |
| `POST /api/v1/runs/{run_id}/cancel` | Sin cuerpo | `200`, instantánea actual; operación idempotente. |
| `POST /api/v1/runs/{run_id}/reviews` | `{base_result_revision,submission}` | `201`, `{result_revision,state,result,validation_report}` dentro de `data`. |
| `GET /api/v1/runs/{run_id}/exports?format=json\|csv` | `format` obligatorio | `200`, descarga del resultado vigente; `409 result_unavailable` si no existe. |

`mode` admite `live|geometry_only|recorded_replay`. `recorded_run_id` es obligatorio solo en replay y debe pertenecer al ámbito autenticado. `run_config` usa el contrato canónico: las unidades de origen confirmadas participan en la huella. No acepta instrucciones libres para ampliar permisos. Modelo y límites se resuelven contra configuración autorizada del servidor; el navegador no recibe la clave del proveedor.

La instantánea Run contiene identificadores y versiones canónicos, `mode`, `state`, marcas temporales, configuración efectiva, contadores consumidos, `result_revision`, `result`, `validation_report`, causa terminal y procedencia de caché/replay; los valores aún inexistentes son `null`. `result` incluye las piezas completas con nombre, rol, estado de etiqueta, cantidades, `dimensions_mm`, contornos y referencias de evidencia. El cliente no reconstruye cantidades a partir del visor. Solo candidatos `entity_level=part` originan piezas; objetos completos o niveles desconocidos quedan en disposiciones `needs_review` con evidencia, sin presentar un mueble entero como componente manufacturable. La altura general de un objeto no se exporta como `thickness`.

### Plano seleccionable y evidencias sin piezas

`GET ledger` permite consultar entidades, vistas, contornos, evidencias, mediciones, observaciones y candidatas de la revisión autorizada, incluidas cotas generales aunque `result.pieces=[]`. Se conserva la misma `candidate_revision` en plano y ledger; el cliente rechaza mezclar revisiones y vuelve a cargarlas. No se expone el ledger completo al proveedor por el hecho de habilitar su lectura al usuario autorizado.

El futuro modelo Pydantic `DrawingPreview` deberá acordar como mínimo `schema_version`, `candidate_revision`, `coordinate_unit` (`mm|source`), unidad fuente y efectiva (admitiendo `null`), límites de vista, primitivas 2D seguras y un mapa de IDs. Cada primitiva enlaza un ID estable de dibujo con sus `source_entity_ids` y, cuando existen, `view_id`, `contour_ids` y `evidence_ids`. Los IDs fuente preservan layout, handle y ruta de inserción mediante los registros del ledger; no se reemplazan por índices de fila. El mapeo permite seleccionar una pieza y resaltar sus vistas, y recorrer una cota general hasta su fuente sin inventar una fila de despiece. Las curvas o entidades no soportadas mantienen una indicación explícita de cobertura.

Con unidades resueltas, las primitivas usan milímetros. Con unidades desconocidas, el plano puede usar coordenadas fuente y muestra «unidad sin resolver»: no contiene puntos etiquetados `points_mm`, medidas métricas inventadas ni un factor implícito de 1. Una entidad fuente puede visualizarse aunque no haya producido un contorno métrico. La vista previa no convierte una proyección en colocación física 3D.

`visualizar_vista` devuelve un `artifact_id` resoluble mediante la ruta de artefactos del mismo run. El servidor busca IDs en su repositorio y comprueba pertenencia y permisos; no acepta paths del cliente, URL arbitrarias, nombres con traversal ni acceso directo al disco. Solo sirve formatos generados y permitidos, con tipo de contenido correcto; una representación SVG deberá sanearse o sustituirse por primitivas seguras/imagen raster, sin scripts o referencias externas. Un ID ajeno o inexistente responde `404`. La preview de DXF 2D no presupone soporte de PDF de entrada o reconstrucción completa de STEP.

Los POST de creación y revisión requieren `Idempotency-Key`. Su ámbito es usuario autenticado + método + ruta + clave; se guarda hash canónico del cuerpo, incluyendo hash de archivo para upload. Repetir contenido devuelve el mismo recurso; reutilizar clave con contenido distinto da `409 idempotency_conflict`. La clave no elude la comprobación de permisos. Cancelar usa el propio run como identidad y no exige clave adicional.

Errores HTTP: `400` para parámetro inválido; `401` sin sesión; `404` para recurso inexistente o fuera de ámbito; `409` para revisión obsoleta o conflicto; `413` para tamaño excesivo; `415` para formato no admitido; `422` para incumplimiento estructural; `429` para admisión saturada, con `Retry-After`; `503` para dependencia no disponible. Los fallos posteriores a `202` se consultan en Run y SSE; no se cambian retroactivamente por una respuesta HTTP de error.

## Archivos, admisión y persistencia

El límite inicial es `max_upload_bytes=20971520`; se verifica mientras se recibe, sin confiar solo en `Content-Length`. Se valida formato real y se almacena con nombre interno generado, sin usar rutas del archivo. `max_entities=100000` limita expansión y análisis. La ingesta no ejecuta texto CAD ni descarga referencias externas. `original_filename` se trata como texto para visualización.

El corpus mecánico auxiliar `engineering-drawings-harness.zip` está auditado en [DATASET.md](DATASET.md); el catálogo CADBLOCK fue descartado como datos de despiece. La presencia de PDF, STEP u otros formatos en el archivo no los habilita como entradas P0. El contrato de upload P0 sigue siendo un DXF individual directamente utilizable; admitir lotes ZIP necesitaría un contrato adicional. Si se ofrece DWG en P1, se conserva el original; sin conversor ODA instalado y verificado, el run termina con causa explícita `conversion_unavailable` y la interfaz propone exportar DXF. Se conservan hashes original/normalizado y manifiesto de conversión. Nunca se presenta un DWG sin convertir como extracción correcta.

SQLite y artefactos en disco son suficientes para el despliegue inicial de un solo host. La transacción de creación guarda run y trabajo pendiente antes de devolver `202`; un ejecutor con reclamación exclusiva procesa fuera del bucle de peticiones. Este diseño no atribuye durabilidad a `BackgroundTasks` de FastAPI ni requiere Redis/Celery. La [documentación de tareas](https://fastapi.tiangolo.com/tutorial/background-tasks/) sirve para delimitar esa elección; no sustituye el repositorio de trabajos.

Se persisten entradas, ledger inmutable, versiones, intentos y contadores, resúmenes de herramientas, informes, resultados y eventos. Resultado y evento terminal se confirman atómicamente. Una interrupción de proceso marca runs activos `failed`, con `worker_interrupted`; no reanuda silenciosamente llamadas ni finalizaciones. Un replay conserva `recorded_run_id`, fecha original y huella; una lectura cacheada identifica el run de procedencia. Ambos permanecen visibles en HTTP y eventos.

## SSE reproducible y observable

Cada run tiene una secuencia entera creciente desde 1, asignada transaccionalmente. El sobre exacto es `{schema_version,run_id,sequence,event_type,timestamp,data}`. `id:` contiene el decimal de `sequence`; `event:` coincide con `event_type`; `data:` contiene el sobre JSON completo en una línea, seguido por una línea vacía. Ejemplo sintético:

```text
id: 7
event: tool_completed
data: {"schema_version":"0.1.0","run_id":"run_demo","sequence":7,"event_type":"tool_completed","timestamp":"2026-11-13T12:00:00Z","data":{"tool_call_id":"tc_2","tool_name":"inspeccionar_candidata","ok":true,"evidence_ids":["ev_demo"],"summary":"Candidato consultado"}}

```

| `event_type` | Contenido de `data` |
|---|---|
| `run_state_changed` | `{previous_state,state,reason_code}`; inicial `previous_state=null`. |
| `tool_started` | `{tool_call_id,tool_name,argument_hash}`. |
| `tool_completed` | `{tool_call_id,tool_name,ok,evidence_ids,summary}`. |
| `validation_issue` | Un `ValidationCheck` canónico fallido/desconocido relevante. |
| `result_committed` | `{result_revision,state}`. |
| `run_finished` | `{state,reason_code,result_revision}`; último evento del run. |
| `provenance` | `{mode,cache_hit,source_run_id,source_timestamp,fingerprint}`. |

`summary` es una descripción breve de la acción o resultado, generada desde datos admitidos. No incluye razonamiento privado, cadena de pensamiento, tokens del proveedor ni prompts completos. Las evidencias y candidatos permiten enlazar la tabla al resaltado 2D. Los detalles del informe se recuperan en GET; SSE no publica blobs CAD ni imágenes incrustadas.

Sin cursor se envía el historial desde el principio. `Last-Event-ID: N` reenvía solo secuencias mayores que N y después sigue en vivo, sin ventana entre ambas fases. Cursor no decimal o negativo da `400`; mayor que el máximo persistido da `409 invalid_event_cursor`. P0 conserva el historial durante la vida del run; una política futura de purga deberá responder `410 event_history_expired` y exigir recarga de la instantánea.

La entrega es al menos una vez: el cliente descarta duplicados por `(run_id,sequence)` y detecta saltos antes de avanzar su cursor. Un comentario `: heartbeat` puede mantener la conexión sin asignar secuencia. En estado terminal se vacía el historial y se cierra; el cliente cierra su `EventSource` al recibir `run_finished`. Reconectar con el cursor terminal puede recibir `204`, evitando reconexiones inútiles. La desconexión del navegador no cancela el run.

El formato, UTF-8 y la reconexión por `Last-Event-ID` siguen [WHATWG EventSource](https://html.spec.whatwg.org/multipage/server-sent-events.html). FastAPI ofrece [respuestas de streaming](https://fastapi.tiangolo.com/advanced/custom-response/); el framing, persistencia y deduplicación siguen siendo responsabilidades de Vexplorer. Se recomienda sesión mediante cookie segura del mismo origen para `EventSource`; las escrituras requieren defensa CSRF. No se ponen credenciales en la URL.

## Revisión, cancelación y exportación

Las revisiones se admiten sobre `completed|needs_review`, con resultado existente y coincidencia exacta de `base_result_revision`. Un conflicto responde `409 stale_result_revision`. El servidor obtiene identidad del revisor de la sesión; un `reviewer_id` enviado por el cliente no autoriza nada. La revisión entrega `Submission`, pasa el mismo validador determinista y crea una revisión nueva, conservando propuesta original, autor, fecha y decisiones. No transforma silenciosamente un run terminal en trabajo agente.

Para que las salidas tempranas sean revisables, el servidor genera, valida y persiste la abstención definida en [HARNESS.md](HARNESS.md), con Result revisión 1, antes de finalizar `needs_review`. Cero candidatas produce listas vacías y una comprobación `unknown/review` de cobertura, causa propuesta `no_supported_part_candidates`; nunca `completed` por vacío. Las candidatas válidas de nivel `object|unknown` y las de identidad ambigua se conservan como disposiciones con evidencia; la abstención no crea piezas ni cantidades artificiales. Un ledger estructuralmente inválido produce `failed` con diagnóstico `invalid_evidence_ledger`, sin inventar evidencias para fabricar un resultado revisable. Los borradores inválidos permanecen separados de Result. Cancelación y plazo mantienen sus estados propios y su prioridad transaccional.

El revisor puede escoger referencias y candidatos, justificar disposiciones y confirmar etiquetas con evidencia o autoridad de revisión. `label_status=confirmed` nunca procede de una afirmación autónoma del LLM. Nuevas unidades, medidas de origen o configuración de vistas requieren nuevo run/revisión de candidatos; el endpoint no reescribe el ledger. Un informe con errores rechaza la revisión; incógnitas conservan `needs_review`. Una revisión validada con al menos una pieza válida, cobertura completa y sin incógnitas obligatorias puede llevar `result.state` de `needs_review` a `completed`, mediante una nueva revisión auditable y sin reejecutar el agente. `Run.state` conserva el desenlace original e inmutable de la ejecución; la interfaz usa `result.state` para el estado del resultado vigente. La revisión se registra en auditoría propia y se devuelve por POST/GET, sin añadir eventos después de `run_finished`.

P0 limita las alternativas a interpretaciones competidoras de una misma ocurrencia; una descomposición alternativa en varias ocurrencias exige regenerar el libro. Las cadenas dimensionales generales `R-015` permanecen en P1 y se informan `not_applicable` en P0 hasta acordar su representación estructurada entre A/B y avisar a C. Una revisión no introduce esas premisas mediante texto libre.

Cancelar gana solo si el run todavía no es terminal al confirmar la transacción. Repetir cancelación devuelve la instantánea; si ya se entregó, conserva ese resultado. Los límites y plazos definidos en [HARNESS.md](HARNESS.md) no se reinician por reconexión, lectura HTTP ni reintento de cliente.

JSON exporta resultado, revisión y procedencia; CSV incluye ID estable de fila, estado, cantidad, dimensiones y referencias, con ausencias explícitas y nombres protegidos contra fórmulas de hoja de cálculo. Un resultado en revisión puede descargarse con esa marca visible. Las cajas 3D son esquemáticas, solo se muestran para piezas con las tres dimensiones respaldadas y unidades resueltas, y no añaden certeza al archivo exportado. Si falta una dimensión, se conserva la lectura 2D y su estado de revisión; no se sustituye el espesor por una altura de objeto. PDF es P1 opcional. La verificación futura de reconexión, concurrencia y revisión se detalla en [TEST_PLAN.md](TEST_PLAN.md).

## Límite de la corrección de identidad en P0

`RunConfig` y el endpoint de revisión propuestos no incorporan nuevas asociaciones físicas ni confirmaciones de ocurrencias de conjunto. La UI P0 permite escoger referencias, etiquetas y alternativas ya sustentadas; si la corrección necesita nueva evidencia de identidad, conserva `needs_review`. Repetir entrada y configuración sin cambios no resuelve esa incertidumbre en un motor determinista. El mecanismo autenticado para introducir tal evidencia, regenerar el ledger e incluirla en el fingerprint queda pendiente de acuerdo A/B y aviso C. Los cambios de unidades y etiquetas de vista sí siguen las entradas propuestas; no se equiparan a confirmar asociación física.

## Ampliación de API para T11–T12

La revisión 0.1.0 no permite todavía confirmar nuevas descomposiciones físicas ni obtener presupuestos. Acordar operaciones versionadas para consultar/proponer escenarios, revisar componentes y premisas, buscar comparables y generar/consultar estimaciones. No reutilizar un endpoint de edición de etiquetas para cambiar identidad o número de piezas.

Cada operación debe conservar ámbito de acceso, actor, versiones y procedencia. La estimación referencia el escenario/despiece y catálogo exactos; una revisión posterior no cambia retroactivamente su importe. La traza debe mostrar recuperación y cálculo resumidos sin datos privados innecesarios; las referencias reservadas de evaluación nunca se exponen al agente. Rutas, eventos y esquemas concretos quedan pendientes del acuerdo A/B y aviso C, sin afirmar endpoints implementados.

## Efecto de la descarga de PlankAssembly

[PlankAssembly](PLANKASSEMBLY.md) es un recurso local de preparación/evaluación, no un endpoint implementado. No aceptar sus programas JSON como si fueran planos DXF ni servir respuestas privadas a través de `/artifacts`, `/ledger` o `/drawing`. Las futuras vistas admitidas se cargarán como documentos derivados, con formato y procedencia comprobados; no se han generado aún.

No se ha subido este dataset al VPS. Su almacenamiento local y autorización de descarga no habilitan redistribución pública. Esta nota no altera las rutas, campos ni acuerdos de contrato pendientes.
