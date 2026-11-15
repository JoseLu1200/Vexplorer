# Precedentes: ideas 2.1–3.5 del brainstorming de embeddings

Implementación en `backend/app/precedentes/` de las ideas 2.1 a 3.5 de [BRAINSTORMING_EMBEDDINGS](BRAINSTORMING_EMBEDDINGS.md). Incluye backend, API y tests; **no incluye interfaz**. Se integra sobre el nivel 1 (ideas 1.1–1.7, ver `team/sergio.md`) en la rama `embeddings`.

## Integración con el nivel 1

- **Umbrales calibrados (1.2):** 2.1 y 2.3 usan `similarity.thresholds.resolve_similarity_threshold`, configurable por versión de descriptor y modelo con `VEXPLORER_SIMILARITY_THRESHOLDS_FILE` (generado con `tools/calibrate_similarity.py`, idea 1.1).
  - 2.1 compara el score de cada vecino **relativo al techo de la consulta** (su similitud consigo misma): `geometric_match` puntúa 0 las medidas desconocidas, y sin ese ajuste un vecino idéntico en lo conocido nunca alcanzaría el umbral calibrado para muebles completos.
  - 2.3 aplica a cada candidato el umbral combinado con sus pesos efectivos (`w_geo·umbral_geo + w_sem·umbral_sem`) y se abstiene con `sin_precedentes_suficientes`, el mismo motivo que la búsqueda de similares.
- **Cambio de comportamiento en `POST /api/v1/library/groups` (1.2/1.3):** `threshold` es opcional y, si se omite, ya no vale 0,8 fijo sino `DEFAULT_GROUP_THRESHOLDS` de `similarity/thresholds.py`: 0,85 en modo `geometric` y 0,92 en modo `semantic` (resoluble por versión de descriptor y modelo con `VEXPLORER_SIMILARITY_THRESHOLDS_FILE`). Un cliente que dependiera del 0,8 implícito obtendrá agrupaciones más estrictas (menos pares unidos); debe enviar `threshold` explícito para conservar el valor anterior.
- **Coseno unificado (1.4):** 2.3, 2.6 y 3.3 calculan el coseno con `similarity.math_utils`.
- **Agrupamiento sin encadenamiento (1.3):** 2.4 aplica el mismo principio a piezas, con tolerancia en mm en lugar de score.

## Principios

- Los números (medidas, cantidades, espesores) se comparan con reglas deterministas; el embedding solo aporta la parte semántica.
- Toda sugerencia basada en precedentes es una **hipótesis**, informa de su soporte (n/N, rango, ids de los vecinos) y **se abstiene** por debajo de un mínimo.
- Los datos sintéticos o publicados se declaran como tales; nunca se presentan como coste empresarial.
- No se modifican `contratos/` ni `historico/`: los modelos viven en el propio paquete y se podrán promover con acuerdo A/B.
- Todo `/api/v1/precedentes/*` devuelve **403 en acceso público**, igual que el histórico y la biblioteca.

## Endpoints

Prefijo común: `/api/v1/precedentes`.

| Idea | Método y ruta | Qué hace | Requiere proveedor |
|---|---|---|---|
| 2.1 | `POST /sugerencias` | Sugiere valores desconocidos del descriptor (dimensiones, espesores, material, acabado) a partir de vecinos de la misma familia ordenados por `geometric_match` | No |
| 2.2 | `POST /presupuesto-analogia` | Compara un coste calculado con el rango de costes de comparables del histórico; alerta en múltiplos de la dispersión robusta (MAD) | Solo en modo `semantic` |
| 2.3 | `POST /similares-hibrido` | `score = w_geo·geométrico + w_sem·coseno`, con componentes visibles; si falta el embedding, cae a solo geométrico y lo indica | No (usa vectores guardados) |
| 2.4 | `POST /piezas/gemelas` | Agrupa piezas casi idénticas de distintos orígenes con tolerancia por eje (≤ 50 mm), espesor y material exactos, sin encadenamiento; propone medida estándar | No |
| 2.5 | `POST /embeddings/regenerar`, `GET /embeddings/mantenimiento` | Detecta embeddings obsoletos (revisión, ausencia, corrupción, espacio distinto o huella retirada); por defecto solo simula. Con `incluir_sin_huella` marca también los vectores sin sello. Tras guardar en la biblioteca puede regenerar en segundo plano (opcional, ver Mantenimiento automático) | Sí, para regenerar |
| 2.6 | `POST /embeddings/espacio/verificar`, `POST /embeddings/espacio/rotar`, `GET /embeddings/espacio`, `GET /embeddings/espacio/historico` | Huella del espacio con frases de control; detecta deriva del modelo y permite rotar la referencia. Cada embedding generado se sella con la huella vigente, de modo que una rotación marca como obsoletos los vectores anteriores | Sí, para verificar y rotar |
| 2.7 | `python -m tools.evaluar_recuperacion` | Precision@k, recall@k, MRR y nDCG@k con juicios de relevancia (`evaluation/recuperacion/`) | No |
| 3.1 | `POST /piezas/lotes` | Agrupa piezas de varios pedidos por (espesor, material, acabado) exactos y coloca cada ocurrencia en tableros con un *nesting* 2D determinista por guillotina (first-fit decreasing; ancho de sierra, margen y giro de 90° configurables). Devuelve por grupo tableros, colocaciones, aprovechamiento real por tablero y total, y piezas no colocadas con motivo; conserva la estimación por superficie como referencia (`estimacion.metodo` frente a `nesting.metodo`) | No |
| 3.2 | `POST /busqueda` | Traduce una frase a filtros estructurados con un LLM (herramienta `aplicar_filtros_busqueda`, esquema estricto) y filtra de forma determinista; con `filtros` no llama al LLM | Sí, solo con `consulta` |
| 3.3 | `POST /imagen/indexar`, `POST /imagen/similares` | Mecanismo de embeddings de imagen de las vistas del plano; sin proveedor configurado | Sí (no hay ninguno en producción) |
| 3.4 | `POST /decisiones`, `GET /decisiones/resumen` | Registra aceptaciones o rechazos de comparables y recomienda pesos (AUC por componente); nunca se aplican solos | No |
| 3.5 | `POST /herrajes/registros`, `GET /herrajes/registros`, `POST /herrajes/sugerencias` | Almacén propio de herrajes por registro histórico y sugerencia por precedentes; probado solo con datos sintéticos | No |

## Mantenimiento automático del espacio (2.5 y 2.6)

Implementado en `backend/app/precedentes/mantenimiento.py`; no modifica `contratos/`.

- **Candado persistente:** `CandadoPersistente` guarda candados con *lease* e intervalo mínimo en `precedentes_espacio.sqlite3` (tabla `candados`). La adquisición y la comprobación del intervalo ocurren en una transacción `BEGIN IMMEDIATE`, por lo que es seguro entre hilos, workers y procesos; un proceso caído libera el candado al expirar el lease (300 s) y la regeneración lo renueva antes de cada elemento. El reloj es de pared (`time.time`), no monotónico. Verificar y rotar siguen compartiendo el intervalo mínimo (429 `verificacion_reciente`) y los candados ocupados devuelven 409 `operacion_en_curso`.
- **Huella ligada al espacio:** la identidad de un embedding es (modelo, dimensiones, `descriptor_version`) más el sello de huella. Como `EmbeddingMetadata` no tiene campo para la huella (cambiarlo exige acuerdo A/B), el sello vive en la tabla `sellos_embedding` por `cache_key`. Se sella con la referencia vigente de (modelo, dimensiones) cada vez que se genera un vector (regeneración y guardado de la biblioteca); si no hay referencia no se sella y nunca se llama al proveedor para crearla. Un vector sellado con una huella distinta de la vigente es obsoleto (`huella_retirada`), y un `descriptor_version` de los metadatos distinto del del descriptor cuenta como `espacio_distinto`.
- **Regeneración sin caché cuando la huella cambia:** `cache_key` no incluye la huella, así que la regeneración de un elemento `huella_retirada` (o con un sello ajeno a la huella vigente) vuelve a embeber y sobrescribe la entrada de caché en lugar de reutilizarla.
- **Tras guardar en la biblioteca:** `tras_guardar_biblioteca` (una llamada en `backend/app/main.py`, tras `repository.save_library_item`) anota el embedding vigente del elemento, marca como reemplazado (`embeddings_reemplazados`, visible en `GET /embeddings/mantenimiento`) el `cache_key` anterior si cambió, y sella el vector recién generado. La biblioteca guarda una sola fila por run, así que "revisiones anteriores" son los vectores que dejó de referenciar esa fila. Con `VEXPLORER_PRECEDENTES_REGENERACION_AUTO=1` y solo para guardados semánticos, encola en un hilo de fondo la regeneración de ese elemento si está obsoleto (por ejemplo, un acierto de caché de un espacio retirado), con el mismo candado persistente; si está ocupado, se omite. Desactivado por defecto: no genera gasto. Los fallos del enganche se registran y nunca cambian la respuesta 201.
- **La regeneración tras guardar nunca cambia la revisión guardada:** en ese camino ignora `revision_obsoleta`, actúa solo por motivos de espacio (`huella_retirada`, `espacio_distinto`, `embedding_ausente`, `embedding_corrupto`), nunca sobre elementos sin embedding, y reconstruye el descriptor de la revisión ya guardada. Toda escritura de una regeneración (también la manual) pasa por `registrar_guardado`, de modo que `biblioteca_vigente` no se desincroniza.
- **Robustez del candado:** un salto atrás del reloj de pared no deja el candado colgado (se considera expirado si `expira_en - ahora > ttl`; el intervalo mínimo nunca espera más que el propio intervalo). La regeneración hace *fencing*: renueva el lease justo antes de escribir en la caché y antes de `save_library_item`; si lo perdió devuelve un informe parcial (`abortado: true`, resto `omitido` con `candado_perdido`) sin escribir. Una BD de candados bloqueada devuelve 503 `candado_no_disponible` y un fallo al liberar no convierte una operación terminada en error (el lease expira solo).
- **Sellado sin ventanas:** la huella vigente se toma antes de embeber y solo se sella con ella si no cambió; en el guardado de la biblioteca solo se sella si la referencia no se creó después de generarse el vector. En caso contrario el sello previo se borra y el vector queda desconocido. El sello guarda también `version_frases`: una versión distinta de la vigente es `huella_desconocida`, no `huella_retirada`.
- **Cola de fondo acotada y por app:** `ColaMantenimiento` (una instancia por `create_app`, en `app.state.cola_mantenimiento`) usa un hilo, máximo 16 tareas pendientes deduplicadas por elemento y descarta el exceso con un aviso. `apagar()` (en el apagado de la app, `backend/app/main.py`) descarta lo pendiente de **esa** app y la tarea en curso aborta en su siguiente latido; no cancela las colas de otras apps del mismo proceso. La parte síncrona del enganche usa un timeout de SQLite de 2 s y, si no puede registrar, se omite con un aviso sin afectar al 201.
- **Sin pérdida de guardados concurrentes:** antes de escribir, la regeneración (manual o de fondo) relee el elemento y lo omite (`modificado_durante_regeneracion`) si cambió `created_at`, `result_revision` o `descriptor_fingerprint` mientras se embebía. El repositorio no tiene escritura condicional, así que queda solo la ventana entre esa relectura y `save_library_item`.
- **Esquemas antiguos:** `ttl_s` y `version_frases` se declaran en el `CREATE TABLE`; la migración de BD antiguas ignora `duplicate column name` si otro proceso migró antes. Un `sqlite3.DatabaseError` (incluida una BD ilegible) devuelve 503 `candado_no_disponible` en lugar de un 500.

## Almacenamiento

Cada funcionalidad con estado usa su propio SQLite en el directorio de datos: `precedentes_espacio.sqlite3`, `precedentes_decisiones.sqlite3`, `precedentes_imagen.sqlite3` y `precedentes_herrajes.sqlite3`. No se tocan las tablas existentes.

La rotación explícita de espacio invalida las entradas de `embedding_cache` de la biblioteca para el modelo y dimensiones correspondientes **antes** de guardar la nueva huella. La respuesta incluye `embeddings_invalidados`. Después se puede inspeccionar `POST /embeddings/regenerar` con `simular:true` y regenerar en lotes con `simular:false`. Hasta entonces, las búsquedas semánticas no reutilizan los vectores borrados; el híbrido declara su fallback geométrico. Esta operación no invalida el almacén separado del histórico económico.

## Calibración utilizable por el servidor

El informe estadístico y la configuración del runtime son salidas distintas:

```console
python -m tools.calibrate_similarity --db RUTA/vexplorer.sqlite3 --thresholds-output thresholds.json --json
```

Configure `VEXPLORER_SIMILARITY_THRESHOLDS_FILE` con la ruta a `thresholds.json`. El fichero contiene `similarity`, `group` y `near_duplicate`, separados por versión de descriptor y modelo. Son sugerencias empíricas del corpus utilizado: generar el fichero no acredita calidad con datos reales ni sustituye juicios de relevancia independientes.

## Límites conocidos

- **Umbrales:** 2.1 y 2.3 heredan los valores por defecto de 1.2 mientras no exista un archivo de calibración real. Los múltiplos de dispersión de 2.2 y el umbral de 3.3 (obligatorio en la petición) siguen sin calibrar.
- **2.3** sigue usando el texto embebido actual, que incluye medidas e incógnitas (hallazgos H1/H2). Cambiarlo exige una nueva `descriptor_version` y volver a embeber la biblioteca.
- **2.6:** la huella no está en `EmbeddingMetadata` (requeriría acuerdo A/B), sino en sellos por `cache_key` dentro de `precedentes_espacio.sqlite3`. Las referencias son por (modelo, dimensiones, versión de frases), no por `descriptor_version`. La verificación sigue lanzándose a mano: nada la programa. Un sello es tan fiable como la disciplina de verificar y rotar; al rotar el espacio se invalidan las entradas de `embedding_cache` correspondientes (y se devuelve `embeddings_invalidados`) bajo exclusión mutua con la regeneración.
- **Vectores sin sello** (todos los anteriores a esta función, o generados sin referencia): no se marcan por defecto, para no declarar obsoleta toda la biblioteca en el primer despliegue; `incluir_sin_huella` los marca y los regenera (con coste). Hasta entonces una rotación no los detecta.
- **2.5 regeneración tras guardar:** si el candado está ocupado se omite y el elemento se recoge en la siguiente regeneración manual; no hay cola persistente. La cola de fondo es de un hilo por proceso. Si dos elementos comparten `cache_key`, regenerar uno sobrescribe el vector de ambos. Un proceso caído nunca bloquea más de 300 s; si otro sufre una pausa mayor que el lease pierde el candado (comprobado también por expiración en `renovar`) y la regeneración se aborta en el siguiente latido, sin escribir.
- **Marcas de reemplazo:** solo se registran guardados posteriores a este mecanismo; no hay purga de entradas de caché huérfanas.
- **3.3 y 3.5** son mecanismos sin datos ni modelo reales.
- **3.1** el *nesting* es una heurística de guillotina (no óptima: puede usar más tableros que el mínimo posible). Parámetros de la petición: `tablero_largo_mm`/`tablero_ancho_mm` (2440×1220), `kerf_mm` (3), `margen_mm` (0), `permitir_rotacion` (true) y, por pieza, `rotable` (true; `false` si tiene veta). La veta se supone paralela al largo del tablero (eje X); una pieza sin girar ocupa su `largo` en X. El kerf no se aplica en los bordes. El límite de 3000 ocurrencias físicas (suma de cantidades que caben en tablero) es **por lote**: un lote que lo supera no se nestea (`nesting: null`, `nesting_omitido: "demasiadas_ocurrencias"`), conserva su `estimacion` y no impide calcular el resto; además hay un presupuesto de 15 000 ocurrencias nesteadas por petición (los lotes que no entran, tomados por superficie decreciente, quedan con `nesting_omitido: "limite_total_de_calculo"`). Las piezas con largo, ancho o cantidad desconocidos siguen en `sin_clasificar` (una cantidad desconocida no se convierte en 1 unidad). `piezas_que_no_caben` indica que el número por superficie no es un plan de corte realizable y deriva del nesting (área útil en micrómetros, margen y `rotable`). No considera tableros parciales/retales, vetas por material ni coste de corte.
- **2.2:** MAD cero produce `dispersion_nula`, sin alerta estadística; los costes comparables y el rango siguen visibles. Los candidatos no estimables no consumen el cupo de comparables válidos.
- Los errores de validación del cuerpo usan el 422 por defecto de FastAPI (`detail`), como `api/history.py`; los errores de negocio usan el sobre `{schema_version, data, error}`.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q backend/tests/test_precedentes_*.py
```

Estado y evidencias en [team/pablo.md](../team/pablo.md).
