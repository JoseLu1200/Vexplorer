# Auditoría histórica, corpus y preparación del laboratorio semántico

## 1. Alcance y fecha de corte

Este documento describe dos estados distintos:

1. El producto Vexplorer en el commit base `42095101ac93c9c39d62271a62333ed924f8e51c`, anterior al laboratorio semántico.
2. El corpus local y la preparación experimental creada en la rama aislada `experiment/semantic-furniture` el 14 de noviembre de 2026.

Las afirmaciones sobre backend, harness, similitud y costes pertenecen al commit base. Otras ramas y cambios paralelos pueden haber ampliado el repositorio después de esa referencia. Este documento no atribuye esas ampliaciones al producto base ni evalúa un despliegue posterior.

La auditoría usó archivos locales, manifiestos, código y pruebas. No usó claves, `.env`, respuestas privadas de evaluación ni llamadas pagadas. Los datos de terceros permanecen fuera de Git.

## 2. Resultado resumido

El producto base ya tenía una biblioteca de revisiones, tres versiones de descriptor, similitud geométrica y embeddings de texto mediante OpenAI. Ese recorrido partía de resultados estructurados y revisados por Vexplorer. No clasificaba planos arbitrarios en categorías generales de mobiliario.

El producto base también ofrecía comparables y estimación. El servicio de comparables económicos usaba tres referencias sintéticas incluidas en código y no consultaba la biblioteca semántica. La estimación heredada elegía el primer comparable y escalaba un coste de material por área. El cálculo específico de mesas tenía fórmulas y catálogo versionado, aunque el catálogo de desarrollo usaba tarifas sintéticas.

El laboratorio nuevo preparó un control local con 118 DXF candidatos de CADBlock. Admitió 117, excluyó uno por geometría con Z no nula y congeló 89 grupos antes de entrenar o ajustar transformaciones. Las cuatro etiquetas proceden de carpetas editoriales mezcladas. Sirven como proxy de evaluación, no como verdad humana.

PlankAssembly ofrece 26.707 modelos oficiales de tableros y referencias paramétricas. El archivo original no contiene planos 2D ni precios. El repositorio ya tenía un adaptador de seis casos, pero ese ensayo no ejecutó inferencia ni demostró diversidad semántica.

## 3. Estado histórico del producto en `4209510`

### 3.1 Descriptores disponibles

El contrato definía tres espacios incompatibles por versión:

| Versión | Entrada principal | Familia admitida | Contenido |
|---|---|---|---|
| `furniture-v1` | Flujo legado de vistas montadas | `rectangular_shelving` o `unknown` | dimensiones, roles, estructura, material, acabado y campos desconocidos |
| `furniture-v2` | Vistas de piezas separadas | `rectangular_shelving` o `unknown` | campos de v1, espesores, estado de clasificación y características por pieza con estado `observed`, `confirmed` o `unknown` |
| `furniture-v3` | Mesa rectangular revisada | `rectangular_table` | perfil `rectangular_table_v1`, componentes aceptados, cantidades, dimensiones y referencias de tarifa de material |

Los modelos están en [`backend/app/contratos/modelos.py`](../../backend/app/contratos/modelos.py#L1302). `FurnitureDescriptorV2` comienza en la línea 1343 y `FurnitureDescriptorV3` en la 1376 del snapshot auditado.

[`build_descriptor`](../../backend/app/semantic/descriptor.py#L206) elegía la versión según `input_semantics`:

- `_build_parts_descriptor` construía v2 desde candidatos de montaje y piezas revisadas.
- `_build_table_descriptor` exigía una mesa completada, programa seleccionado y componentes aceptados. Rechazaba una revisión incompleta con `table_revision_not_accepted`.
- El flujo legado producía v1 y limitaba la familia a estantería rectangular o desconocida.

[`descriptor_fingerprint`](../../backend/app/semantic/descriptor.py#L239) calculaba SHA-256 sobre JSON canónico. [`semantic_text`](../../backend/app/semantic/descriptor.py#L244) convertía el descriptor estructurado en texto con familia, estructura, dimensiones, roles, material, acabado, desconocidos y, según versión, piezas o componentes.

Estas funciones describían un resultado ya interpretado. No extraían una categoría libre desde píxeles, entidades DXF o nombres de archivo.

### 3.2 Proveedor de embeddings de texto

[`OpenAIEmbeddingProvider`](../../backend/app/semantic/embeddings.py#L39) aceptaba una cadena y llamaba a `/embeddings` con:

- modelo configurado;
- `encoding_format: float`;
- dimensión configurada;
- timeout HTTP de 30 segundos.

El proveedor validaba longitud, finitud y norma no nula. También exigía que el modelo devuelto coincidiera con el solicitado. La interfaz no aceptaba imágenes ni geometría.

[`EmbeddingSettings`](../../backend/app/agente/config.py#L42) fijaba estas condiciones:

- modelo por defecto `text-embedding-3-small`;
- 256 dimensiones por defecto;
- rango admitido de 1 a 1536 dimensiones;
- proveedor disponible solo si existía `OPENAI_API_KEY` y el modelo era `text-embedding-3-small`.

[`embedding_cache_key`](../../backend/app/semantic/embeddings.py#L22) incluía versión del descriptor, modelo, dimensiones, formato y texto normalizado. No incluía proveedor, revisión de pesos, imagen ni versión de preprocesado porque el contrato solo contemplaba OpenAI y texto. [`EmbeddingMetadata`](../../backend/app/contratos/modelos.py#L1388) restringía `provider` al literal `openai`.

### 3.3 Similitud geométrica y semántica

[`geometric_match`](../../backend/app/similarity/service.py#L58) comparaba descriptores de la misma versión. Aplicaba cocientes `min/max` a dimensiones, cantidades por rol y espesores:

| Descriptor | Pesos fijos |
|---|---|
| v1 | dimensiones 0,70; roles 0,30 |
| v2 | dimensiones 0,60; roles 0,25; espesor medio 0,15 |
| v3 | dimensiones 0,60; roles 0,25; espesor ponderado por cantidad 0,15 |

Un campo ausente aportaba cero a su cociente. El servicio no aprendía esos pesos y el snapshot no contenía calibración contra juicios humanos de relevancia.

[`semantic_match`](../../backend/app/similarity/service.py#L92) calculaba coseno si modelo, dimensión y versión de descriptor coincidían. [`geometric_groups`](../../backend/app/similarity/service.py#L101) y [`semantic_groups`](../../backend/app/similarity/service.py#L130) unían pares que superaban un umbral y devolvían componentes conexos reproducibles.

Los grupos admitían transitividad: A podía enlazar con C a través de B aunque el par A-C no alcanzara el umbral. La explicación del contrato ya advertía que un grupo no demostraba identidad ni intercambiabilidad. El endpoint aceptaba un umbral de cliente dentro de `[-1, 1]`; el valor por defecto de la solicitud era 0,8 en [`backend/app/main.py`](../../backend/app/main.py#L84).

### 3.4 Biblioteca semántica

Los endpoints de biblioteca y similitud vivían en [`backend/app/main.py`](../../backend/app/main.py#L738):

- `POST /api/v1/runs/{run_id}/library` construía el descriptor de la revisión solicitada.
- El modo `openai` generaba o recuperaba un embedding de caché.
- `GET /api/v1/library` permitía filtrar por versión de descriptor.
- `POST /api/v1/runs/{run_id}/similarity` devolvía vecinos geométricos o semánticos.
- `POST /api/v1/library/groups` agrupaba elementos por umbral.

`LibraryItem` guardaba `run_id`, revisión, etiqueta, descriptor, fingerprint, fecha y metadatos de embedding. No guardaba coste, horas, moneda, fecha económica ni alcance de presupuesto. La etiqueta era un campo aportado al crear el elemento; el backend no la infería como clase general.

### 3.5 Harness acotado

[`AgentLimits`](../../backend/app/agente/runner.py#L40) fijaba por defecto:

- 15 llamadas al modelo;
- 30 llamadas a herramientas;
- 120 segundos de plazo total;
- dos reparaciones de validación.

El módulo tenía tres bucles: [`run_agent`](../../backend/app/agente/runner.py#L124), [`run_parts_agent`](../../backend/app/agente/runner.py#L236) y [`run_table_agent`](../../backend/app/agente/runner.py#L366). Los tres validaban argumentos Pydantic, IDs permitidos, revisión y presupuesto.

El flujo legado entregaba un escenario que el motor ya había anunciado. El flujo de piezas seleccionaba un candidato de montaje existente. La mesa permitía proponer un programa, pero [`run_table_agent`](../../backend/app/agente/runner.py#L527) exigía referencias a medidas y evidencias del ledger. El backend rechazaba IDs ajenos.

El modo visual de mesa:

- limitaba la selección a tres vistas;
- exigía una solicitud explícita por ID;
- generaba un PNG con marcas ligadas al ledger;
- declaraba la imagen como contexto, no como fuente de medidas;
- exigía al menos una vista antes de proponer cuando el servidor activaba visión.

Este harness acotaba el comportamiento del agente. No constituía un clasificador de camas, sofás, mesas y equipamiento comercial sobre un corpus externo.

### 3.6 Comparables y costes desconectados de la biblioteca

[`backend/app/historico/service.py`](../../backend/app/historico/service.py#L1) definía tres estanterías sintéticas en una constante. [`find_comparables`](../../backend/app/historico/service.py#L38) puntuaba dimensiones, material y acabado. No consultaba `LibraryItem`, embeddings ni grupos semánticos.

[`estimate_result`](../../backend/app/estimacion/service.py#L6):

1. exigía una revisión completada;
2. elegía el primer comparable;
3. conservaba un coste fijo;
4. escalaba material por área total confirmada;
5. devolvía `hours=None`.

El resultado incluía la advertencia «Histórico y tarifas sintéticos; estimación no apta para compra».

El cálculo de mesas seguía otro recorrido. [`estimate_table_costs`](../../backend/app/estimacion/table_costs.py#L259) calculaba conceptos de material, canto, operaciones, mano de obra, acabado y preparación a partir de un catálogo. [`backend/app/estimacion/cost_catalog.py`](../../backend/app/estimacion/cost_catalog.py#L13) marcaba el catálogo de desarrollo como sintético y ajeno a una cotización de proveedor. Un catálogo empresarial configurado podía sustituirlo, pero el snapshot no incluía tarifas empresariales verificadas.

El producto base separaba estas superficies:

```text
revisión Vexplorer -> descriptor -> biblioteca -> similitud

revisión Vexplorer -> tres comparables sintéticos -> estimación heredada

mesa aceptada -> catálogo de tarifas -> cálculo trazable de mesa
```

No existía un enlace que recuperara vecinos de la biblioteca y usara sus costes reales como base económica.

## 4. Inventario local de datos

### 4.1 CADBlock 2D

Ruta local: `../cadblock_2d/`, respecto a la carpeta `Vexplorer` principal. La preparación conserva datos fuera de Git.

El manifiesto local registró 500 bloques seleccionados:

| Resultado | Cantidad |
|---|---:|
| DXF descargados | 497 |
| DWG descargados | 497 |
| Pares planos admitidos por la auditoría de descarga | 490 |
| Pares apartados por geometría Z no nula | 7 |
| Bloques ausentes por HTTP 404 | 3 |
| DXF con entidades `DIMENSION` | 497 |

Los ausentes fueron `doors-elevation-38`, `living-room-59` y `table-lamps-01`. El corpus ocupaba 82,49 MiB entre DXF y DWG. Los archivos STEP y GLB de una descarga anterior no permanecían en el workspace.

Cada DWG acompaña al DXF del mismo objeto. Contar ambos formatos duplicaría la muestra. La preparación semántica usó DXF.

La auditoría estructural de los 497 DXF observó:

- lectura correcta con ezdxf 1.4.5;
- cero duplicados exactos por SHA-256 entre los 497 archivos del corpus;
- layouts `Model` y `Layout1` en todos los archivos;
- `Layout1` vacío en todos los casos;
- vistas de planta, alzado y lateral reunidas en modelspace, según el dibujo;
- unidades declaradas como metros en el manifiesto de descarga.

`cadblock_2d/evidence/sample-metric.dxf` era una copia auxiliar fuera del manifiesto. El benchmark no la contó.

### 4.2 Distribución completa por biblioteca CADBlock

| Biblioteca | DXF disponibles | Categoría amplia de origen |
|---|---:|---|
| sofas | 43 | furniture |
| living-room | 39 | furniture |
| doors-elevation | 37 | doors |
| kitchen-sinks | 35 | kitchen |
| simple-tables | 32 | furniture |
| ranges | 32 | kitchen |
| kitchen-appliances | 31 | kitchen |
| toilets | 29 | sanitary |
| trees-elevation | 29 | trees |
| trees-plan | 27 | trees |
| palm-trees | 24 | trees |
| sanitary-ware | 23 | sanitary |
| buffets | 22 | kitchen |
| beds | 21 | furniture |
| dining-sets | 21 | furniture |
| bathroom-set | 18 | sanitary |
| bathtubs | 13 | sanitary |
| doors-plan | 10 | doors |
| restaurant-layouts | 8 | furniture |
| trees-3d | 3 | trees |

La suma amplia era: furniture 164, kitchen 120, sanitary 83, trees 83 y doors 47. Estas categorías describen bibliotecas del sitio, no anotaciones adjudicadas para aprendizaje automático.

### 4.3 `cadblock_bulk`

`../cadblock_bulk/` conservaba automatización, catálogos, índices y evidencia de descarga. No contenía modelos CAD binarios en la fecha de auditoría. El laboratorio no lo usó como conjunto de muestras.

### 4.4 Fixtures de `Vexplorer/data`

[`data/planos_demo`](../../data/planos_demo/README.md) contenía 18 DXF sintéticos propios:

- siete casos de estantería o mueble montado;
- cuatro mesas montadas;
- siete casos de vistas de piezas separadas.

Los manifiestos declaran procedencia propia y ausencia de activos de terceros. Estos casos prueban contratos, invariancias, campos desconocidos y recorridos de desarrollo. No forman un benchmark ciego y no acreditan generalización sobre planos empresariales.

## 5. Benchmark CADBlock congelado

### 5.1 Selección de clases

[`DEFAULT_CATEGORIES`](../../tools/semantic_lab/dataset.py#L13) selecciona cuatro bibliotecas con al menos 20 candidatos:

| Etiqueta proxy | Candidatos | Admitidos | Contenido observado |
|---|---:|---:|---|
| sofas | 43 | 43 | sofás, sillones, chaise longues, otomanas y algunas mesas auxiliares |
| simple-tables | 32 | 32 | mesas y escritorios con sillas, más algún mueble de oficina |
| buffets | 22 | 21 | mostradores, carros, refrigeración y líneas de cocina comercial; no aparadores domésticos |
| beds | 21 | 21 | camas, grupos de camas y casos con mesillas |
| **Total** | **118** | **117** | |

El laboratorio excluyó `curved-end-serving-counter-four-round-wells-plan-metric.dxf` porque contenía geometría Z no nula. La exclusión aparece en el manifiesto con `reason: nonzero_z_geometry`.

`living-room` y `dining-sets` permiten una variante opcional de seis clases. Ambas bibliotecas mezclan escenas y objetos que se solapan con sofás y mesas. El control principal usa cuatro clases y mantiene sus defectos taxonómicos visibles.

### 5.2 Etiquetas proxy y verdad humana

El benchmark conserva `label_source: cadblock_library_proxy`. Las etiquetas no prueban la identidad funcional del mueble. Una persona tendría que revisar cada caso para crear verdad humana.

La carpeta `buffets` muestra el riesgo: el nombre puede sugerir aparadores, pero los archivos representan equipo de restauración. `simple-tables` incluye sillas en las vistas y algún archivador. Un clasificador puede aprender composición de escena o convenciones del dibujante en lugar del tipo de mueble.

Las métricas deben llamarse «clasificación de biblioteca proxy» o «recuperación por categoría proxy». No deben presentarse como precisión general de reconocimiento de mobiliario.

### 5.3 Extracción geométrica

[`extract_dxf`](../../tools/semantic_lab/features.py#L191) lee modelspace y expande `INSERT` de forma recursiva. El extractor admite:

- `LINE`;
- `LWPOLYLINE` y `POLYLINE`, incluidos segmentos curvos que ezdxf convierte a path;
- `ARC`, `CIRCLE`, `ELLIPSE` y `SPLINE` mediante discretización;
- `3DFACE`, `SOLID` y `TRACE` si sus coordenadas Z son cero.

El extractor ignora texto, atributos, cotas, hatch, leaders, puntos y líneas infinitas. Rechaza un dibujo sin geometría soportada, geometría degenerada, valores no finitos y cualquier primitiva admitida con Z no nula.

El laboratorio mantiene todos los contornos y vistas de un DXF dentro de una muestra. No trata planta, alzado y lateral como tres objetos físicos.

### 5.4 Normalización y 27 features

[`_normalize`](../../tools/semantic_lab/features.py#L93) traslada la caja mínima al origen y divide por el mayor lado de la caja. Esa operación conserva relación de aspecto y elimina traslación y escala global.

[`_features`](../../tools/semantic_lab/features.py#L139) calcula 27 valores finitos:

| Grupo | Cantidad | Contenido |
|---|---:|---|
| Caja y complejidad | 6 | ancho y alto normalizados, logaritmo de aspecto, logaritmos de caminos y segmentos, longitud total normalizada |
| Tipos de entidad | 8 | fracción de líneas, polilíneas, arcos, círculos, elipses, splines y caras |
| Orientación | 8 | histograma de orientación no dirigida, ponderado por longitud |
| Distribución radial | 5 | histograma de radios de puntos medios, ponderado por longitud |

El vector no contiene etiqueta, ruta, nombre, título, texto del dibujo, ID de grupo ni número de entidades ignoradas. La última exclusión evita que la cantidad de textos o cotas funcione como pista editorial.

[`_observation_text`](../../tools/semantic_lab/features.py#L178) produce un descriptor textual a partir de seis observaciones numéricas. No lee texto libre del plano ni el nombre de la categoría.

### 5.5 Render canónico

[`_render`](../../tools/semantic_lab/features.py#L116) genera PNG monocromo de 384 × 384 píxeles:

- fondo blanco;
- geometría negra;
- padding fijo;
- eje Y invertido para presentación;
- sin texto, cotas, nombres ni leyenda.

El manifiesto usa `image_path` solo para localizar el PNG. Las montajes QA llevan etiquetas para inspección humana y viven fuera del directorio de renders que consumen los modelos.

### 5.6 Deduplicación y grupos

[`_group_records`](../../tools/semantic_lab/dataset.py#L114) crea componentes por unión de:

1. SHA-256 exacto del DXF;
2. firma geométrica normalizada por traslación y escala;
3. SHA-256 del render canónico;
4. familia conservadora derivada del nombre, usada solo como metadato de partición.

Los 497 DXF no tenían duplicados exactos. El benchmark terminó con 117 muestras y 89 grupos. Quince grupos contenían más de un archivo y reunían 43 muestras. Esos grupos proceden de firmas canónicas o familias de variante, no de archivos byte a byte idénticos.

La heurística nominal elimina palabras de cantidad, tamaño, asiento y tipo genérico para mantener juntas variantes evidentes, como versiones de dos y tres plazas del mismo diseño. Esta regla reduce fuga, pero no demuestra independencia entre los 89 grupos. Puede dejar variantes no detectadas o agrupar diseños distintos.

### 5.7 Partición congelada

[`_split_groups`](../../tools/semantic_lab/dataset.py#L139) asigna grupos completos con semilla `20261114` antes de cualquier ajuste de escalado, PCA, clasificador o umbral.

| Etiqueta | Train | Validation | Test | Total |
|---|---:|---:|---:|---:|
| beds | 15 | 3 | 3 | 21 |
| buffets | 15 | 3 | 3 | 21 |
| simple-tables | 24 | 5 | 3 | 32 |
| sofas | 28 | 6 | 9 | 43 |
| **Total** | **82** | **17** | **18** | **117** |

Ningún `group_id` cruza particiones. El conjunto test debe permanecer cerrado durante selección de features, normalización, PCA, hiperparámetros, fusión y elección de método. Validation decide la configuración; test confirma una configuración congelada una sola vez.

### 5.8 Manifiesto y hash

Ruta externa:

```text
D:/Vexplorer-semantic-lab/data/core/manifest.json
```

SHA-256:

```text
15f2448895806c85c0647da72413bfc8de39f5a6fe71d535121303f1d03f00fe
```

El manifiesto usa `schema_version: 1`. Cada muestra contiene:

- `id`;
- `source_path`;
- `image_path`;
- `label` y `label_source`;
- `group_id`;
- `split`;
- `features`;
- `text`.

Los campos de identidad y rutas no son inputs de representación. El laboratorio guardó `qa_train_montage.png` y `qa_validation_montage.png` junto al manifiesto para inspección visual.

### 5.9 Reproducción

Desde la raíz del worktree:

```powershell
python -m tools.semantic_lab.dataset `
  --source "C:/datasets/cadblock_2d" `
  --output-dir "D:\Vexplorer-semantic-lab\data\core"
```

El CLI también acepta `--categories`, `--seed` y `--image-size`. El código está en [`tools/semantic_lab/dataset.py`](../../tools/semantic_lab/dataset.py) y [`tools/semantic_lab/features.py`](../../tools/semantic_lab/features.py).

[`tests/test_semantic_lab_dataset.py`](../../tests/test_semantic_lab_dataset.py) comprueba:

- invariancia ante nombre y traslación;
- invariancia ante añadir o quitar texto del plano;
- agrupación de duplicados y variantes antes del split;
- valores finitos;
- exclusión explícita de geometría Z.

La verificación del bloque de datos obtuvo 5 pruebas aprobadas. La suite compartida del worktree obtuvo 457 pruebas aprobadas en la ejecución registrada por el agente de datos.

## 6. PlankAssembly

### 6.1 Inventario oficial

[`docs/PLANKASSEMBLY.md`](../PLANKASSEMBLY.md) registra:

| Campo | Valor |
|---|---:|
| JSON presentes | 27.692 |
| Modelos únicos en splits oficiales | 26.707 |
| Train | 24.039 |
| Valid | 1.329 |
| Test | 1.339 |
| JSON fuera de splits | 985 |
| Modelos listados y ausentes | 0 |
| JSON sin `normal` | 6.520 |
| Modelos oficiales sin `normal` | 6.427 |
| Tableros físicos por modelo oficial | mínimo 3, mediana 8, máximo 19 |

La primera fila de `planks` representa la envolvente global. Un consumidor debe excluirla de la lista física y conservar los índices originales de `attach`.

El ZIP no contiene DWG, DXF, SVG ni PDF. Contiene programas de cuboides y asociaciones en milímetros. Tampoco incluye material, acabado, mecanizados, tolerancias, precio, coste u horas.

La ausencia de IDs repetidos entre splits no descarta variantes, escalados o diseños equivalentes. El corpus necesita agrupación por proyecto o familia antes de usarlo como prueba de recuperación.

### 6.2 Adaptador existente de seis casos

El snapshot base ya incluía [`tools/prepare_plankassembly.py`](../../tools/prepare_plankassembly.py#L139), aunque documentación anterior describía la exportación como pendiente.

El adaptador:

- toma entre 1 y 10 modelos, con límite predeterminado de 6;
- excluye `planks[0]` del dibujo físico;
- genera tres proyecciones rectangulares en capas `ORTHO_FRONT`, `ORTHO_TOP` y `ORTHO_SIDE`;
- fija unidades DXF en milímetros;
- crea ZIP y hashes reproducibles;
- separa el DXF público de la referencia privada con cuboides, normales disponibles e índices;
- admite `normal` ausente.

[`docs/ACEPTACION_PRODUCCION.md`](../ACEPTACION_PRODUCCION.md#adaptación-reproducible-de-plankassembly) registra seis casos tomados del inicio de `valid`: cinco `development` y uno `holdout`. Los seis hashes de familia fueron distintos.

Ese ensayo no ejecutó Vexplorer, no midió inferencia, no probó diversidad semántica y no descartó duplicados del corpus amplio. Los seis modelos reales tenían `normal`; un fixture propio cubrió la ausencia del campo.

Las proyecciones proceden del programa 3D reservado. No son planos originales de fabricación. Un benchmark debe impedir que el agente reciba JSON, cuboides, `attach`, normales, nombres o archivos vecinos.

## 7. Licencias, procedencia y uso propio

### 7.1 CADBlock

El manifiesto local identifica `https://cadblock.org/` como fuente y `https://cadblock.org/terms-and-conditions/` como condiciones. La auditoría técnica no convierte esas condiciones en una licencia de redistribución, entrenamiento o uso comercial.

Antes de usar CADBlock fuera del experimento local, el equipo debe:

1. revisar los términos vigentes y conservar una copia fechada;
2. confirmar por escrito si permiten el uso previsto, los derivados, la evaluación y la exposición a proveedores de modelos;
3. mantener atribución y procedencia por archivo;
4. evitar publicar DXF, DWG, renders derivados o pesos que memoricen activos hasta resolver los permisos;
5. retirar el corpus si el titular no autoriza el alcance.

### 7.2 PlankAssembly

La ficha de datos declara CC BY-NC-ND 4.0. El código del proyecto oficial usa AGPL-3.0. Cada licencia cubre artefactos distintos.

La descarga autorizada desde Hugging Face no acredita permiso comercial ni permiso para publicar derivados. La cláusula NC plantea un conflicto directo con una PoC empresarial si el uso supera investigación interna no comercial. La cláusula ND requiere revisión jurídica antes de distribuir DXF, renders u otras transformaciones del dataset.

El equipo debe obtener autorización adicional antes de:

- usar el dataset en un servicio comercial;
- entregar derivados a clientes o terceros;
- publicar ejemplos, vistas o modelos entrenados;
- mezclar los datos con un corpus empresarial redistribuible.

### 7.3 Límites documentados en este trabajo

El repositorio y el laboratorio mantienen corpus, pesos y artefactos grandes fuera de Git. Los manifiestos registran fuente, URL, revisión, hash y condiciones declaradas por cada publicador. PlankAssembly también separa los DXF públicos de las referencias paramétricas privadas usadas por el adaptador.

Estas convenciones describen la preparación observada. No amplían las licencias ni acreditan permiso comercial, de redistribución o de publicación de derivados. Los enlaces de las secciones 7.1 y 7.2 conservan las condiciones de las fuentes; cualquier alcance adicional depende de esas condiciones o de un permiso del titular.

## 8. Riesgos de validez

### 8.1 Fuga de etiquetas

Nombres de carpeta, rutas y títulos revelan las etiquetas CADBlock. El manifiesto los conserva como metadatos, pero los modelos no deben recibirlos. Un pipeline que construya texto desde `source_path`, `id`, `label` o `group_id` invalida el benchmark.

Los textos y cotas del plano también pueden reflejar la biblioteca o el estilo del autor. El render y las features los excluyen. Cualquier modelo que lea el DXF original por su cuenta reabre esa vía de fuga.

### 8.2 Variantes entre splits

La firma canónica y la heurística nominal reducen variantes cruzadas. No prueban que los 89 grupos sean proyectos independientes. La revisión humana debe identificar series de producto, escalados, escenas equivalentes y dibujos derivados antes de presentar test como estimación de generalización.

### 8.3 Etiquetas mezcladas

Las cuatro clases combinan tipo de objeto, escena y dominio comercial. El score puede premiar estilo gráfico, número de vistas, presencia de sillas o densidad de líneas. Una matriz de confusión por proxy no demuestra comprensión constructiva.

### 8.4 Tamaño y balance

Test contiene 18 muestras: tres camas, tres buffets, tres simple-tables y nueve sofas. Una sola predicción cambia mucho las métricas de las clases pequeñas. El informe debe incluir intervalos o conteos, macro-F1, balanced accuracy y resultados por clase. Accuracy global oculta ese problema.

### 8.5 Relevancia de vecinos

Compartir carpeta no garantiza que dos dibujos sean vecinos útiles para producción. La evaluación de retrieval necesita juicios humanos por pares o listas, con criterios separados para apariencia, construcción, material y proceso.

### 8.6 Costes

CADBlock y PlankAssembly carecen de precios y horas empresariales. Un buen clasificador de categoría no valida una estimación económica. El producto necesita histórico de proyectos con revisión, alcance, moneda, fecha, coste real, precio ofertado, horas, material, acabado y mecanizados.

### 8.7 Geometría admitida

El laboratorio proyecta todas las vistas de modelspace en un lienzo canónico. No segmenta planta, alzado y lateral ni comprueba correspondencia entre ellas. La discretización de curvas pierde detalle fino. El extractor rechaza Z no nula y puede omitir entidades no soportadas.

## 9. Condiciones para una evaluación defendible

El equipo debería completar estos controles antes de usar resultados para decidir producto:

1. Un técnico revisa etiquetas y marca objetos mezclados, escenas y casos ambiguos.
2. El equipo define `project_id` o `product_family_id` independiente del nombre de archivo.
3. El split se regenera por proyecto y conserva un test que el equipo de modelos no inspecciona.
4. El pipeline registra exactamente qué campos alimentan cada representación.
5. Escalado y PCA se ajustan con train; validation selecciona configuración; test se abre una vez.
6. Retrieval usa relevancia adjudicada, no coincidencia de carpeta como único criterio.
7. Un corpus empresarial separado enlaza cada plano revisado con su versión económica.
8. El equipo obtiene permisos compatibles con uso empresarial y derivados.

## 10. Lectura correcta de los resultados

El benchmark CADBlock puede responder:

- si una representación separa cuatro bibliotecas proxy en este corpus;
- si vecinos comparten una categoría editorial;
- si el método conserva invariancias a nombre, traslación y anotaciones;
- si la agrupación no cruza las particiones congeladas.

No puede responder:

- si Vexplorer reconoce cualquier mueble;
- si identifica piezas fabricables desde un plano pobre;
- si dos muebles requieren el mismo proceso de taller;
- si un vecino aporta un precio válido;
- si el sistema generaliza a planos de la empresa;
- si los datos permiten uso comercial o redistribución.

Los informes deben separar clasificación proxy, recuperación visual, composición constructiva y estimación económica. Cada tarea requiere anotaciones y métricas propias.

## 11. Inventario cruzado posterior

Una inspección posterior mantuvo el core 117 congelado y comprobó entradas públicas de otros corpus. La pantalla de la app ejecutó [`extract_drawing`](../../backend/app/geometria/extraction.py#L568) en el snapshot histórico `42095101ac93c9c39d62271a62333ed924f8e51c`. La pantalla de features usó el extractor del laboratorio en ese mismo worktree. Los resultados siguientes no describen una API nueva, una rama posterior ni el despliegue vigente.

Los artefactos viven fuera de Git:

```text
D:/Vexplorer-semantic-lab/cross-dataset/inventory.json
D:/Vexplorer-semantic-lab/cross-dataset/INVENTORY.md
```

La pantalla de compatibilidad obtuvo estos resultados:

| Conjunto | Resultado del extractor de features | Resultado de `extract_drawing` |
|---|---|---|
| Engineering pilot v3 | 14 de 14 DXF | 14 de 14; todos `needs_review` |
| PlankAssembly test público | 10 de 10 DXF | 10 de 10; todos `ready` |
| PlankAssembly valid público | 6 de 6 DXF | 6 de 6; todos `ready` |
| CADBlock fuera de las cuatro clases | 373 de 379 DXF | 379 de 379; 270 `ready`, 109 `needs_review` |

Tres CADBlock fallaron en el lector experimental de features al acceder a vértices de `3DFACE` o `SOLID`; otros tres tenían Z no nula. Vexplorer leyó los seis. La inspección registró ese hallazgo y no cambió el extractor ni reajustó el core.

La comparación equivalente contra el snapshot actual de la app pertenece a [PRUEBA_APP_OTROS_DATASETS](PRUEBA_APP_OTROS_DATASETS.md) cuando ese documento se incorpore. Sus resultados no deben mezclarse con esta ejecución histórica.

El histórico público `public_furniture_history_2026-11-14` contiene cuatro presupuestos académicos de un solo proyecto. No enlaza cada registro con un plano técnico individual. Sirve para importación económica y procedencia, no para evaluar un embedding visual.

El inventario recomienda tres familias para una prueba heterogénea sin crear etiquetas:

1. `dining-sets`, 21 DXF y etiqueta proxy de origen;
2. `doors-elevation`, 37 DXF como control arquitectónico OOD;
3. 16 PlankAssembly públicos como conjunto sin clase semántica, evaluado por `family_hash` y estabilidad de vecinos.

Los 14 DXF mecánicos del piloto Engineering forman otro control OOD. Deben medir abstención o distancia al índice de muebles, no entrenar una clase artificial junto a mobiliario.
