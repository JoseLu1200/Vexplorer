# Dataset candidato para Vexplorer: ingeniería y referencias parciales

## Inventario vigente

Hay dos fuentes descargadas: **PlankAssembly**, para preparar mobiliario de tableros, y **engineering_dataset**, como control mecánico auxiliar. La auditoría de PlankAssembly está en [PLANKASSEMBLY](PLANKASSEMBLY.md): 26.707 modelos oficiales, 985 JSON adicionales, mm y vistas 2D pendientes. Las secciones siguientes auditan exclusivamente el ZIP mecánico; sus 422 archivos no incluyen PlankAssembly.

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

**Estado: auditoría documental del candidato `engineering-drawings-harness.zip`, sin código de producto ni suite de aplicación ejecutada. La suite del preparador mecánico se documenta en [PILOTO_DATASET](PILOTO_DATASET.md).** El paquete aporta conjuntos mecánicos con planos PDF y piezas CAD aisladas. Mejora la disponibilidad de ejemplos con listas de materiales, pero no constituye un benchmark completo de despiece de mobiliario desde DWG/DXF. Su admisión se propone por tarea y evidencia, sin cambiar automáticamente el alcance del producto.

## Inventario comprobado del archivo

La lectura del directorio ZIP confirma **422 archivos**, **239215084 bytes descomprimidos** y ausencia de nombres duplicados o rutas absolutas/con `..`. El SHA-256 del archivo recibido es `d199804e4a164fc4b5ccca31abb7e066feae41d8713565234d49c4a383ee9968`. El directorio raíz es `engineering_dataset/`. No se ejecutó `download_assemblies.py` ni ningún ejemplo de código incluido; sus instrucciones se trataron como contenido no confiable.

| Extensión o tipo | Archivos | Uso declarado |
|---|---:|---|
| JSON | 174 | Índices, manifiestos, entidades, cotas, medidas, caras y cámaras. |
| PNG | 117 | 112 imágenes Orla y cinco previews adicionales. |
| PDF | 74 | 50 Julius de Waal, diez Bench Vise y 14 Orla. |
| DXF / DWG / STEP | 14 de cada formato | Representaciones relacionadas de 14 componentes Orla. |
| Parquet | 5 | Catálogos Orla; no cinco conjuntos de entrenamiento independientes. |
| Markdown | 3 | README de las tres subcolecciones. |
| Otros | 7 | Un Python, un TXT, un CSV, un JPG y tres archivos sin extensión. |

`index.json` contiene **65 tareas**: 51 de `assembly_drawing_interpretation` —50 paquetes Julius y Bench Vise— y 14 de `single_part_cad_dimension_extraction`. Distintas páginas, vistas y formatos del mismo objeto no aumentan el número de ejemplos independientes. La cifra de 158 páginas corresponde a los 50 PDF Julius; no al total del ZIP.

## Tres subcolecciones, tres tipos de referencia

| Subcolección | Material disponible | Referencia realmente incluida | Uso y límite |
|---|---|---|---|
| `conjuntos/bench_vise/` | Un PDF de conjunto y nueve PDF de componentes. | `bench_vise_reference.json`: BOM de 12 referencias y 22 unidades; dimensiones revisadas de Jaw Pad únicamente. | Piloto PDF P1, pendiente de adaptar evidencias y roles. No es entrada DXF ni mueble de paneles. |
| `conjuntos/julius_de_waal/` | 50 PDF, 158 páginas; manifiesto con páginas de BOM, detalles y trazos vectoriales. | Planos fuente, sin JSON de referencia por pieza validado. | Selección y anotación humana P1. Evidencia de BOM no equivale a un oráculo completo. |
| `cad_piezas/OrlaMechCAD-Nano/` | 14 pares DWG/DXF/PDF y 14 STEP; sidecars y vistas. | 370 registros de cotas del publicador y mediciones geométricas derivadas, con relaciones entre activos. | P0 para extracción de cotas de piezas aisladas. No evalúa la cantidad o descomposición de un conjunto. |

### Bench Vise: referencia útil, cobertura parcial

En esta revisión se reabrieron y renderizaron el PDF de conjunto y `Jaw Pad.pdf`, ambos de una página. Inspeccionó visualmente la BOM de **12 filas**, cuya suma es **22**: `1+1+2+2+2+4+1+1+1+1+2+4`. Nueve referencias tienen plano individual; tres referencias normalizadas no lo tienen. La cantidad de Jaw Pad es **2**, tomada de la BOM, y no del número de vistas.

Las cotas visibles de Jaw Pad son ancho **69.85 mm**, alto **44.45 mm** y espesor **5.00 mm**. El JSON transcribe esos valores y sus equivalentes `0.06985`, `0.04445` y `0.005` m. Solo esta referencia tiene `dimensions_reviewed=true`; las otras once conservan dimensiones `null`. La verificación no se extiende a todas las medidas de las otras piezas, ajuste, material, tolerancias o aptitud de fabricación.

El aviso **DO NOT SCALE DRAWING** impide presentar distancias medidas en píxeles o puntos PDF como cotas nominales automáticas. La propuesta para PDF utilizará cotas escritas, unidad explícita y referencias de página/región. Resolver conflictos y geometría requiere reglas específicas; un PDF vectorial tampoco entrega por sí solo una escala física fiable.

### Julius de Waal: planos y BOM, sin etiquetas completas

El manifiesto contiene 50 entradas y suma 158 páginas. Todas declaran `annotation_status: source drawing only; no gold per-part JSON`, así como uso personal y no comercial. Registran la revisión de catálogo `a0eb762c1c5be76f3340c69c52fe6ea6db2ab63e`, URLs de origen y hashes. Sus listas `bom_evidence_pages`, `part_detail_evidence_pages` y `vector_pages` son índices de evidencia suministrados, no etiquetas verificadas de todas las piezas.

Se extrajo y revisó el texto de la primera de las tres páginas de `09B-50-00.pdf`: presenta una lista de 19 referencias, incluidos subconjuntos, y secciones tituladas. No se revisaron visualmente todas sus páginas ni los 50 paquetes. Nombres, números de componente, subconjuntos y cantidades deben transcribirse y cotejarse antes de convertirlos en resultado esperado. No todos los renglones de una BOM tienen por qué corresponder a una pieza fabricada indivisible.

### Orla: cotas estructuradas, no BOM de 14 conjuntos

La inspección de los 14 `dimensions.json` confirma **419 registros**: **370** de tipo `dimension` y **49** de tipo `dimension_style`. De las 370 cotas, 356 declaran `raw_measurement_unit=drawing_unit` y 14 `degree`; las angulares no deben normalizarse como longitudes en mm. Hay 50 `text_override` no vacíos y factores de escala diversos, incluidos valores negativos. El valor bruto, texto mostrado, estilo, marco y unidad deben interpretarse por separado.

Los registros incluyen handle, entidad, puntos de definición, bloque, estilo y referencias al texto gráfico. Son adecuados para contrastar extracción y procedencia; no son etiquetas semánticas independientes. Los estados `verified` que aparecen dentro de sidecars pertenecen al publicador. No equivalen a una verificación nueva realizada por Vexplorer.

El README declara cinco tablas Parquet con 14 filas de dibujos, 14 de piezas, 14 de documentos, 14 de mediciones y 28 relaciones `depicts_part`/`rendered_from`. Los cinco archivos están presentes; esta auditoría de metadatos no abrió sus filas por falta de `pyarrow`. Las relaciones visibles en JSON vinculan cada STEP provisto con un dibujo y un identificador externo. El esquema `orla-mech-cad` del publicador se conserva como formato de entrada, sin convertirlo en el contrato de Vexplorer.

## Comprobaciones CAD independientes y alcance

La auditoría CAD abrió **14/14 DXF** con `ezdxf.readzip`. Contó 370 entidades `DIMENSION` y otras cuatro `ARC_DIMENSION` en las bases de entidades. El cotejo por handle confirmó que los 370 registros JSON corresponden exactamente a las 370 `DIMENSION`; las cuatro `ARC_DIMENSION` no están en `dimensions.json` —handles `FEE` y `FF3` en `drawing_87852…`, `4FD` y `50C` en `drawing_bcb355…`—. La cobertura del sidecar no debe describirse como todas las cotas del DXF. Los encabezados `$INSUNITS` indican **11 archivos sin unidad declarada (`0`) y tres en mm (`4`)**. La declaración de unidad de un sidecar o su emparejamiento con STEP no autoriza a convertir los once casos a mm silenciosamente.

Un caso observado en `drawing_1b796…`, handle `5319`, devuelve aproximadamente `67.00000000006793` mediante `ezdxf.get_measurement()`, mientras `actual_measurement` del DXF y `raw_measurement` JSON contienen `44.66666666671191`, el factor es `2/3` y el texto mostrado es `45`. No son campos intercambiables: multiplicar otra vez el valor bruto por el factor produciría otra medida. Antes de fijar un oráculo, documentar qué campo y representación se comparan.

En DWG se inspeccionaron encabezados `AC1015`, `AC1024` o `AC1032`, sin reapertura mediante un lector DWG. En los 14 STEP se encontró textualmente un `MANIFOLD_SOLID_BREP` por archivo y declaración `SI_UNIT(.MILLI.,.METRE.)`. Eso no acredita validez topológica, volumen, colisiones o correspondencia dimensional mediante un kernel independiente. La suma de 349 caras procede de los sidecars, sin validación geométrica nueva de ese total. `source_context.json` declara `origin=provided_step`, correspondencia individual con dibujo y unidad mm basada en la fuente. STEP permanece referencia opcional P1 y no sustituye la entrada DXF.

`verification.json` declara 50 hashes PDF contrastados con Git LFS, 336 artefactos Orla contrastados con catálogos y controles estructurales. Su propio alcance limita la revisión semántica a ejemplos del README. Estas afirmaciones recibidas se separan de la comprobación nueva del inventario, JSON, CAD y dos PDF descrita arriba. No se presentan como 65 interpretaciones correctas de Vexplorer.

## Admisión propuesta P0/P1

**P0:** admitir selectivamente los 14 DXF Orla para extracción de cotas, normalización explícita y trazabilidad, conservando casos de unidad desconocida y texto sobrescrito como pruebas negativas o de revisión. Mantener un fixture propio de paneles rectangulares para despiece, rotulado como sintético. Un resultado correcto sobre una pieza mecánica no demuestra conteo, agrupación o despiece de muebles.

**P1:** usar Bench Vise como primer piloto de interpretación de conjunto PDF, con BOM como objetivo separado y Jaw Pad como control dimensional limitado. Julius requiere seleccionar paquetes, transcribir referencias y anotar medidas antes de evaluación cuantitativa. PDF necesitaría evidencia de página/región y semántica mecánica; son propuestas sujetas a acuerdo A/B, no capacidades actuales. No se amplía de forma implícita el producto a mecanizado o reconstrucción 3D general.

La admisión manual de cada caso deberá registrar tarea, assembly/componente, licencia, unidades, formatos permitidos como entrada, referencia excluida del agente, campos revisados, discrepancias y revisor. Rechazar o conservar para revisión los ejemplos sin evidencia suficiente. No completar medidas faltantes a partir de convenciones ni usar la envolvente STEP como definición automática de largo/ancho/espesor de una pieza de carpintería.

## Entrada, oráculo y particiones

Separar tres pistas: extracción CAD de pieza, lectura de BOM PDF e interpretación completa de conjunto. En extracción, el agente recibe el DXF/DWG autorizado; `dimensions.json`, tablas de mediciones, STEP y caras se reservan como referencias cuando sean el objetivo. Si recibe esas cotas estructuradas, la tarea será interpretación de sidecars y deberá informarse así. En PDF, la BOM visible forma parte de la entrada legítima; su transcripción de referencia permanece oculta. `bench_vise_reference.json` nunca se entrega al agente que está siendo evaluado.

Congelar particiones por **assembly** y familia, no por página, vista, formato o archivo. Mantener juntos conjunto, detalles, PDF, DXF/DWG, STEP, PNG, sidecars, espejos y revisiones del mismo diseño. En Orla, la unidad mínima es el componente emparejado completo; comprobar parentesco antes de repartir placas o soportes similares. En Julius, detectar proyectos consecutivos o subconjuntos compartidos: el README del catálogo advierte que algunos PDF contienen varios proyectos y que hubo división manual.

No se fijan aún cantidades train/dev/test: faltan familias y etiquetas admitidas. Bench Vise y las muestras ya inspeccionadas se destinan a desarrollo/demo, no a reservado ciego. Antes de una evaluación, listar también las muestras declaradas como vistas por el preparador —`09B-50-00`, `01-04-01-03-03`, `11-01-00`, Bench Vise y SLOTTED RIB BRACKET— y excluir su familia del holdout. Usar IDs opacos para ocultar nombres que revelen clase o medidas; conservar texto y cotas que realmente están dentro del plano. Separar pista ciega y pista con contexto externo.

Dos revisores deberán contrastar la referencia con el plano, conservar fuente y discrepancias y congelar el oráculo antes de ejecutar el holdout. Informar resultados por tarea y campo, con denominadores: cotas, unidades, referencias/cantidades BOM y correspondencias. Sin esas etiquetas, reportar cobertura de lectura y observaciones cualitativas; no porcentajes de exactitud de despiece.

## Procedencia y condiciones declaradas

- **Julius de Waal:** [catálogo del recopilador](https://non-bin.github.io/juliusDeWaal/) y URLs originales en el manifiesto. El paquete y sus avisos declaran uso personal/no comercial. No se interpreta como permiso para redistribución pública o entrenamiento comercial.
- **OrlaLabs:** [OrlaMechCAD-Nano 1.0.0](https://huggingface.co/datasets/OrlaLabs/OrlaMechCAD-Nano), con `LICENSE` incluido y declaración [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). Mantener atribución, versión y cambios; un uso comercial requiere resolver la licencia correspondiente.
- **Bench Vise:** [repositorio del autor](https://github.com/Amir-souhail/Mechanical-Bench-Vise), commit `fb6590c09e9d1622e94a2e3e5df06b48a8dc03ae` en `source_manifest.json`. Su README declara MIT; se conserva esa declaración, sin afirmar una revisión externa de titularidad o de todas las condiciones.

Los permisos declarados son distintos por subcolección; no existe una licencia única del ZIP que los sustituya. Conservar originales y avisos en el espacio autorizado. El paquete documental y repositorio público no deben incorporar esta colección recibida: entregar documentación, procedencia y fixtures propios hasta resolver cualquier distribución concreta.

## Decisión y contratos

`cadblock-2d.zip` queda archivado y descartado como dataset de despiece porque sus bloques no aportan la referencia necesaria para esa tarea. Su auditoría anterior no se usa como evaluación de este candidato.

Se recomienda admitir el nuevo paquete como **material de desarrollo por tareas y referencias parciales**, con revisión manual. No se declara aptitud de mobiliario de una colección mecánica. [CONTRATOS_DATOS.md](CONTRATOS_DATOS.md) y [TEST_PLAN.md](TEST_PLAN.md) deberán reflejar las tareas acordadas antes de implementar. Conforme a la instrucción del usuario, cualquier contrato implementado tendrá Pydantic como única fuente de verdad y requerirá acuerdo A/B para cambiarlo; este documento únicamente plantea decisiones, sin modificar contratos ni añadir código de producto.

## Datos aún necesarios para el objetivo de la transcripción

El corpus mecánico descrito es auxiliar para el hito técnico. [PlankAssembly](PLANKASSEMBLY.md) ya aporta referencias paramétricas de mobiliario descargadas y auditadas. Faltan generar y revisar sus entradas 2D, admitir su uso según licencia y conseguir planos pobres reales e histórico con atributos y costes/horas fiables. Disponer de programas de forma no equivale a disponer de una evaluación industrial preparada.

T11 debe separar físicamente entrada y referencia, generar variantes empobrecidas auditadas y particionar por familia/proyecto antes de crear derivados. T12 necesita un histórico que excluya el propio caso de prueba y sus duplicados. Los datos sintéticos son útiles para comprobar el mecanismo y deben identificarse como tales; no acreditan resultados reales de despiece o presupuesto. Procedimiento y criterios en [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md).
