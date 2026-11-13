# Demo y operación de una instancia

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

**Estado: guion y procedimiento futuros.** Vexplorer no está desplegado en este paquete ni se han ejecutado pruebas de aplicación. La auditoría de `engineering-drawings-harness.zip` está en [DATASET.md](DATASET.md); analizar sus archivos no demuestra un producto funcionando. No se ha enviado correo, presentado candidatura ni realizado entrega externa.

El contrato `0.1.0` es una propuesta pendiente de acuerdo A/B y aviso a C. Sus futuros modelos Pydantic serán la única autoridad para JSON y esquemas de herramientas; las pantallas siguientes no fijan otro contrato. [API_Y_EVENTOS.md](API_Y_EVENTOS.md) describe rutas y revisiones, y [HARNESS.md](HARNESS.md) la abstención y presupuestos.

## Preparación y alcance de la demo

P0 demuestra extracción de un DXF real admitido de Orla y comportamiento de despiece sobre un fixture propio de paneles, claramente rotulado. El corpus tiene 14 piezas CAD aisladas y 51 conjuntos PDF; no son 65 ejemplos equivalentes de despiece de muebles. PDF Bench Vise es un piloto P1 pendiente de acuerdo A/B y evidencias página/región; no se presenta como soporte de entrada actual.

Preparar un DXF Orla revisado y un fixture propio con tres vistas de una balda `600 × 400 × 18`, cantidad `1` respaldada. Para una salida en revisión, retirar una evidencia de espesor del fixture sin inventar otra medida. Tener resultado manual esperado y, cuando exista, una grabación identificada por ejecución y fecha. Respetar las condiciones de uso de [DATASET.md](DATASET.md); el paquete documental y repositorio público no incluyen el corpus recibido.

Si el DXF real no declara unidades, mostrar «unidad sin resolver» y coordenadas fuente. Once de los 14 DXF Orla están en ese caso; solo tres declaran mm. La relación con un STEP no confirma unidades ni espesor automáticamente. Confirmar unidades requiere nueva ejecución y fingerprint; no se simula una corrección por el endpoint de revisión del resultado.

## Guion de menos de tres minutos

| Tiempo | Acción | Evidencia visible |
|---|---|---|
| 0:00–0:30 | Abrir un DXF real admitido | Fuente, modo, unidad conocida o pendiente; preview seleccionable y medidas/cotas disponibles. No prometer despiece de la pieza mecánica como mueble. |
| 0:30–0:55 | Seleccionar una cota y mostrar su procedencia | IDs de entidad/evidencia, estilo y valores separados cuando corresponda. Traza SSE de acciones, sin razonamiento privado. |
| 0:55–1:25 | Abrir fixture propio de paneles rotulado | Hover fila→tres observaciones→fuente; un candidato físico y cantidad `1`. No contar vistas. |
| 1:25–1:55 | Mostrar resultado en revisión y una revisión respaldada | Result revisión `1` conservado y nueva revisión `2`. `Run.state` original inmutable; pantalla usa `result.state` actual. Si falta evidencia, conservar desconocido. |
| 1:55–2:20 | Descargar JSON/CSV del resultado | IDs, dimensiones resueltas o `null`, cantidades, disposiciones y estado. Caja 3D solo con tres dimensiones respaldadas y etiqueta «esquemático». |
| 2:20–2:50 | Mostrar abstención o fallo controlado y Plan B | Resultado sin piezas pero revisable; alternativamente DWG/ODA ausente con `conversion_unavailable`. `geometry_only` o replay siempre rotulados. |

Reservar diez segundos para terminar. La duración es un objetivo del guion, no una latencia medida. Si se usa replay, mostrar ID y fecha de origen sin presentarlo como ejecución en vivo. La grabación no debe ocultar una espera para simular rendimiento instantáneo.

El hover se apoya en GET `/api/v1/runs/{run_id}/ledger` y `/drawing`, con la misma `candidate_revision`; el artefacto se obtiene por `/artifacts/{artifact_id}`. También funciona para evidencia general cuando `pieces=[]`. Con unidad desconocida, preview `source`, sin `points_mm` inventados. No mostrar una tabla vacía como pérdida de la fuente.

`R-015` es siempre `not_applicable` en P0. El ejemplo de cadena `18+564+18=600` queda como control futuro P1 hasta estructurar sus premisas. La colisión genérica P0 también es `not_applicable`: el solape de proyecciones o cajas no acredita interferencia física.

## Abstención y revisión que deben verse

Con ledger íntegro y evidencia insuficiente, el servidor construye `pieces=[]` y una disposición `needs_review` por candidata. Debe validar y resolver esa propuesta, persistir Result revisión `1`, informe y evento antes de terminar. Cero candidatas conserva listas vacías y comprobación `R-018=unknown/review`, causa `no_supported_part_candidates`; el resultado es `needs_review`, no `completed` por vacío. Un ledger inválido produce `failed/invalid_evidence_ledger`, sin fabricar referencias.

La revisión humana selecciona evidencia y decisiones permitidas, crea otra revisión de Result y conserva anteriores. No reabre el estado terminal de Run ni sobrescribe medidas. Si cambiar unidades, fuente o asociaciones congeladas resulta necesario, abrir otra ejecución. Las alternativas P0 describen una misma ocurrencia; no representar «una pieza frente a varias» mediante selección exclusiva incorrecta.

## Operación en un solo host

La arquitectura prevista combina FastAPI, interfaz JS/HTML, SQLite y artefactos en disco. El trabajo se reclama y ejecuta fuera del bucle HTTP; `BackgroundTasks` no aporta por sí solo durabilidad. Conservar originales, normalizados, conversiones, ledger, resultados y trazas, junto a sus hashes/versiones. Guardar base de datos y artefactos de manera coherente y comprobar restauración antes de depender de una copia.

Configurar el adaptador nativo del proveedor elegido con secretos del servidor e identificador de modelo explícito; no publicar claves en navegador, logs, SSE o exportaciones. No se fijan versiones comerciales ni precios. Las seis herramientas autorizadas son `inspeccionar_candidata`, `obtener_evidencias`, `comparar_candidatas`, `visualizar_vista`, `validar_borrador` y `entregar_despiece`. Ninguna ejecuta shell, red arbitraria o instrucciones escritas en CAD.

Límites iniciales configurables: `max_upload_bytes=20971520`, `max_entities=100000`, `ingest_timeout_s=60`, `oda_timeout_s=30` incluido en ingestión; fase agente `run_timeout_s=120`, `max_model_calls=15`, `max_tool_calls=30`, `max_validation_repairs=2`. Cada intento consume presupuesto; reintentos y reconexiones no lo reinician. Usar reloj monotónico para plazos. Son límites de diseño, no mediciones.

Al arrancar, comprobar escritura, espacio, SQLite, compatibilidad de datos y configuración del proveedor. El upload P0 recibe un DXF individual, no el ZIP completo. Ofrecer DWG P1 solo tras verificar ODA; ausente comunica `conversion_unavailable` y opción de DXF. STEP y PDF incluidos en el corpus no habilitan nuevas entradas por mera presencia.

## Incidencias y Plan B

`geometry_only` debe conservar modo visible y, cuando no haya propuesta respaldada, persistir la abstención revisable. `recorded_replay` conserva ejecución/fecha originales y su etiqueta. Ninguno completa espesores o convierte objetos en componentes por apariencia. Un timeout conserva `timed_out`; cancelación conserva `cancelled`, idempotente y sin entrega tardía. Gana la primera transición terminal confirmada transaccionalmente.

Tras reinicio, los trabajos activos quedan `failed` con `worker_interrupted`; otro intento requiere nuevo run. Desconectar SSE no cancela; reconectar con `Last-Event-ID` recupera secuencias posteriores y la interfaz deduplica por ejecución/secuencia. La caché solo reutiliza una huella completa coincidente —fuente/conversión, unidades/configuración, geometría/pipeline, esquema, prompt y modelo— con procedencia visible.

La comprobación operativa futura será cargar fixture, iniciar, consultar plano/ledger, recorrer hover, reconectar SSE, cancelar un run y exportar otro resultado. Conservar comandos y salidas reales antes de declararla aprobada. El informe de demo distinguirá auditoría del corpus, objetivos del guion y comportamiento medido; [TEST_PLAN.md](TEST_PLAN.md) contiene los casos que aún deben implementarse y ejecutarse.

## Demo de negocio requerida tras T11–T12

El guion anterior presenta el hito técnico. Para demostrar el objetivo completo, sustituir su eje por: plano 2D pobre de un mueble → propuestas de piezas/secciones y dudas → revisión técnica → muebles históricos similares y diferencias → ficha de compras con costes/horas calculados y supuestos visibles. Después de congelar la salida, comparar con el despiece reservado del evaluador.

Identificar claramente casos reales y sintéticos. Si no existen referencias de mobiliario o histórico económico, mostrar únicamente demostración del mecanismo y declarar pendiente la validación de negocio. Presentar abstención o escenarios ante incógnitas; nunca rellenar importes para completar la demo. Ensayar este recorrido y medirlo antes de prometer una duración.
