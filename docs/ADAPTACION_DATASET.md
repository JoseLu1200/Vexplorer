# Adaptación de Vexplorer a los datasets disponibles

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

## Decisión recomendada

Usar `engineering-drawings-harness.zip` como **corpus técnico auxiliar**, con dos tareas explícitas: extracción de información de una pieza CAD e interpretación de conjuntos PDF. Mantener fixtures propios para pruebas independientes y preparar la evaluación de mobiliario con PlankAssembly descargado, sin confundir vistas generadas con planos de fabricación originales.

Esta decisión permite avanzar con datos concretos. No acredita generalización entre mecánica y mobiliario ni soporte automático de todos los formatos del ZIP. La auditoría está en [DATASET.md](DATASET.md); las decisiones técnicas siguen pendientes de implementación y, cuando afectan al contrato, de acuerdo A/B y aviso C.

## Qué problema resuelve cada grupo

| Grupo | Pregunta evaluable | Pregunta que no responde por sí solo |
|---|---|---|
| 14 piezas Orla DXF/DWG | ¿Localizo la cota correcta, interpreto sus factores y conservo su procedencia? | ¿Cuántas piezas forman un mueble y cómo se ensamblan? |
| Bench Vise PDF | ¿Relaciono una referencia de la BOM con su detalle, cantidad y cotas? | ¿He recuperado geometría exacta 3D o validado todas las dimensiones? |
| 50 conjuntos Julius PDF | ¿Reconozco referencias, detalles, secciones y subconjuntos variados? | ¿Tengo una verdad terreno completa por pieza ya revisada? |
| Fixture propio de paneles | ¿Resuelvo un despiece controlado con tres vistas, dimensiones y cantidades conocidas? | ¿Funciona sobre cualquier plano real de carpintería? |

El cambio respecto al dataset anterior es sustantivo: ahora hay listas de piezas, detalles y datos dimensionales. La separación entre CAD de pieza aislada y PDF de conjunto sigue siendo una limitación que debe aparecer en el pitch.

## P0: recorrido principal DXF

**Entrada:** un DXF individual admitido. **Salida:** plano seleccionable, cotas y su evidencia, incidencias, interpretación propuesta y resultado revisable. Para publicar filas de despiece de paneles hace falta identidad física y medidas suficientes.

Casos de desarrollo sugeridos, ya inspeccionados y excluidos de cualquier reservado ciego:

1. **SLOTTED RIB BRACKET**, dibujo `1b79629a…`: unidades mm declaradas y 28 entidades `DIMENSION`. El handle `5319` es un caso de prueba de escala: medida calculada aproximadamente 67, almacenada 44,6667, factor 2/3 y texto visible 45. Evaluar la separación de magnitudes; no anunciar que las 28 cotas ya estén interpretadas por Vexplorer.
2. **HINGE BLOCK**, dibujo `da1b02f1…`: unidad sin declarar. Debe permitir inspección en coordenadas fuente y exigir evidencia explícita antes de publicar milímetros. Que su STEP declare mm no prueba automáticamente la unidad y escala de todas sus vistas DXF.
3. **CHAIN SPROCKET**, dibujo `93716b79…`: caso negativo de curvas, tipos de cota y sobrescrituras. El sistema debe informar cobertura y campos no soportados, sin convertirlo en panel rectangular.

La fuente de expectativas de estos casos se revisará fuera del extractor. Un JSON extraído del mismo DXF sirve de referencia de regresión, pero no es un segundo anotador independiente. Los cuatro `ARC_DIMENSION` adicionales quedan en el inventario de cobertura, aunque el sidecar principal contenga 370 cotas `DIMENSION`.

El fixture de paneles descrito en [EJEMPLOS_CONTRATO.md](EJEMPLOS_CONTRATO.md) se materializará como DXF propio: tres vistas de una pieza 600 × 400 × 18 mm, asociación manual, cantidad 1; una variante omite el espesor y exige revisión. Los ejemplos actuales son documentación y no ese archivo CAD ya generado.

## P1: piloto PDF Bench Vise

Objetivo inicial limitado: obtener la BOM del conjunto, enlazar Jaw Pad con su plano de detalle y presentar cantidad y cotas con origen localizable.

| Campo | Referencia revisada | Evidencia |
|---|---|---|
| Referencias distintas | 12 | BOM de `Mechanical Bench Vise.pdf`, página 1 |
| Unidades totales del conjunto | 22 | Suma de la columna de cantidades |
| Cantidad de Jaw Pad | 2 | Fila 5 de la BOM |
| Ancho / alto / espesor | 69,85 / 44,45 / 5,00 mm | Cotas explícitas de `Jaw Pad.pdf`, página 1 |
| Dimensiones de otras referencias | Sin revisar | Permanecen `null` en la referencia recibida |

No presentar las 22 unidades como 22 referencias diferentes. Una hoja de detalle representa un diseño de pieza; no determina por sí sola la cantidad a fabricar. Tampoco 9 PDFs individuales significan que falten 3 piezas diseñadas: la BOM incluye 3 tipos de elementos normalizados sin plano individual en este paquete.

### Cambios necesarios antes de implementar PDF

- Un adaptador de ingesta que preserve archivo, página, rotación y geometría del documento; extracción determinista de texto/vector y render para inspección.
- Procedencia por página y región, además de los handles CAD. No fabricar IDs que aparenten entidades DXF inexistentes.
- Asociación explícita entre referencia de BOM, detalle y ocurrencias; preservar jerarquía de subconjuntos cuando exista.
- Cotas nominales con tipo, unidad y evidencia. Los PDFs indican que no se mida a escala del dibujo: medir píxeles o puntos de página no reemplaza una cota nominal.
- OCR o visión, si hacen falta, como propuestas auditables fuera del núcleo geométrico determinista. Una lectura incierta necesita revisión antes de promocionarse a dato confirmado.
- Tipos de dimensión y roles mecánicos cuando sean necesarios. No interpretar diámetro, longitud de eje o altura total como espesor de tablero.

A/B deben acordar esos cambios y avisar a C. La documentación no modifica el contrato existente ni anuncia el piloto como ya implementado. Sin esta ampliación, Bench Vise se utiliza para diseñar el caso de evaluación y revisar el futuro flujo, no para fingir ejecución de DXF.

## Entrada, contexto permitido y respuesta esperada

Definir antes de cada evaluación qué ve el sistema:

| Modo | Entrada admitida | Fuera de la entrada |
|---|---|---|
| CAD solo | DXF y configuración de unidades confirmada, si se declara la intervención | `dimensions.json`, medidas STEP, nombres del catálogo usados como etiquetas esperadas |
| Plano PDF | Páginas de conjunto y detalle declaradas para la tarea | `bench_vise_reference.json` y anotaciones de respuesta |
| Asistido | Datos adicionales enumerados y visibles en el informe | Cualquier ayuda no declarada |

La BOM dibujada en una página es entrada legítima si la tarea consiste en leer esa página. El JSON que transcribe la respuesta no se entrega al agente durante esa evaluación. Separar una pista ciega de semántica, donde se ocultan títulos reveladores, de una tarea operacional de lectura de documentos, donde el título puede ser información válida. No mezclar sus métricas.

Las vistas, formatos y sidecars de un mismo diseño permanecen juntos al separar desarrollo y evaluación. Con solo 14 componentes CAD no se necesita una partición de entrenamiento para ajustar pesos; se necesita una selección de regresión y casos nuevos independientes. Ninguna cifra de precisión se publica sin tamaño de muestra, cobertura y protocolo.

## Puertas de decisión para el hackathon

| Puerta | Evidencia para avanzar | Si no se supera |
|---|---|---|
| Unidad y escala | Una cota del DXF reproducida y contrastada | Mostrar coordenadas fuente y revisión |
| Trazabilidad | Selección de fila resalta su fuente correcta | Corregir IDs antes de ampliar semántica |
| Despiece controlado | Fixture propio devuelve cantidad y medidas esperadas | Mantener demo de lectura de cotas y declarar alcance |
| PDF opcional | BOM y Jaw Pad enlazados con citas de página/región, contrato acordado | Conservarlo como piloto posterior |

El orden recomendado prioriza una prueba real de principio a fin. No se añade entrenamiento, ensamblaje 3D general ni soporte de todos los mecanismos para aprovechar el tamaño del archivo.

## Datos aún necesarios para el objetivo de la transcripción

El corpus mecánico descrito es auxiliar para el hito técnico. [PlankAssembly](PLANKASSEMBLY.md) ya aporta referencias paramétricas de mobiliario descargadas y auditadas. Faltan generar y revisar sus entradas 2D, admitir su uso según licencia y conseguir planos pobres reales e histórico con atributos y costes/horas fiables. Disponer de programas de forma no equivale a disponer de una evaluación industrial preparada.

T11 debe separar físicamente entrada y referencia, generar variantes empobrecidas auditadas y particionar por familia/proyecto antes de crear derivados. T12 necesita un histórico que excluya el propio caso de prueba y sus duplicados. Los datos sintéticos son útiles para comprobar el mecanismo y deben identificarse como tales; no acreditan resultados reales de despiece o presupuesto. Procedimiento y criterios en [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md).

## PlankAssembly: siguiente preparación, todavía pendiente

Aplicar [PLANKASSEMBLY](PLANKASSEMBLY.md): seleccionar una muestra, revisar condiciones, generar vistas del conjunto y reservar programas/asociaciones al evaluador. El adaptador debe excluir la envolvente global de las piezas y conservar los índices originales de asociación. Las normales ausentes requieren una política explícita, no una dirección inventada. Registrar escala de render y eventual conversión SVG→DXF; inspeccionar visualmente el resultado y comprobar unidades antes de abrirlo como plano editable. El preparador mecánico actual no realiza estas operaciones.
