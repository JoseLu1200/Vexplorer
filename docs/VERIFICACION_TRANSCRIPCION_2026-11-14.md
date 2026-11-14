# Verificación de la ampliación de la transcripción

Base anterior: `4209510`. Implementación mediante agentes GPT-6.1 Sol y revisión independiente GPT-6 Astra, por solicitud del usuario. Este registro describe evidencia observada; no convierte una suite técnica en aceptación industrial.

## Software añadido

| Necesidad | Implementación | Límite relevante |
|---|---|---|
| Proponer piezas fuera de los perfiles anteriores | Herramientas nativas de propuesta general, medidas de contornos y operaciones referenciadas | Las asignaciones son hipótesis; no hay reconstrucción industrial universal |
| Revisar y preparar despiece | Reemplazar, dividir, combinar y descartar componentes; snapshots inmutables; BOM y SVG/DXF acotados | Representación rectangular esquemática, sin uniones ni colocación certificada |
| Entrada multiformato | DXF, conversión DWG con LibreDWG/ODA y PDF por página | Raster no aporta medidas geométricas; escala PDF requiere confirmación |
| Usar históricos económicos | Import JSON/CSV con fuente, fecha, moneda, alcance y naturaleza real/sintética; atributos o embeddings | Tener el importador no acredita disponer de datos empresariales |
| Estimar costes y horas | Conceptos fijos/unidad/longitud/área/volumen, escenarios comparables, procedencia y abstenciones | No se derivan horas de euros; incompatibilidades y faltantes no se rellenan |
| Evaluar calidad y utilidad | CLI fuera del runtime, predicciones congeladas y referencias privadas, cobertura/errores/tiempos/correcciones | Sin ensayo con técnicos no se afirma ahorro |

## Evidencia de integración observada

- Base previa: 423 pruebas Python y 108 JavaScript.
- Ejecución conjunta del coordinador durante cierre: 520 pruebas Python y 132 JavaScript aprobadas. Hay un aviso externo de deprecación TestClient/httpx; no es un fallo de producto. Los resultados finales posteriores a nuevas correcciones se registrarán al cierre.
- `tools.audit_integral` contra servidor local: 16 comprobaciones, estado `passed`, incluyendo DWG real opcional. En modo local las comprobaciones exclusivas de autenticación productiva quedan marcadas como tales, no como protección verificada.
- Navegador real: propuesta manual, revisión de panel de prueba `1200 × 700 × 30 mm`, cantidad 1 y segunda revisión cantidad 2. La API conserva revisión 1 con una ocurrencia y revisión 2 con dos; se recuperaron ambos SVG por su snapshot.
- PDF raster propio: entrada imagen, selección explícita de página y ejecución live real. El modelo propuso tablero y soportes con referencias a la página; todas las dimensiones permanecieron desconocidas. No se usó OCR ni se midieron píxeles.
- DWG genuino de vanity del corpus local: conversión LibreDWG 0.14 y carga HTTP 201. Dos pares de mobiliario DWG/DXF fueron contrastados por operación: 130 y 896 entidades, unidades y envolventes coincidentes. Esto no demuestra fidelidad para cualquier DWG.
- Conversor Linux probado aisladamente en el servidor con el primer DWG: 130 entidades y normalización de metros a milímetros. La instalación aislada del conversor no constituye el despliegue del nuevo release de la aplicación.

Las evidencias detalladas están bajo `.runtime/transcript-qa/`, fuera de Git. Los originales de terceros, claves, credenciales, bases de datos y referencias privadas no se versionan.

## Diagnóstico de inferencia, separado de aceptación

Se ejecutaron seis entradas públicas del piloto PlankAssembly con GPT-6.1 Sol real. El coordinador congeló las predicciones y sus hashes antes de que el evaluador las puntuara. La muestra es de desarrollo diagnóstico y no un benchmark empresarial ciego.

La pasada v4 produjo 38 tipos de componente frente a 36 tipos de panel de referencia agrupados; el evaluador alineó 33. Esta comparación geométrica por dimensiones no demuestra identidad semántica ni coincidencia exacta de ocurrencias. Se compararon 99 de 108 campos: MAE 0,202 mm y 97/99 dentro de 1 mm. Todos los valores propuestos tenían estado `hypothesis`.

Las cantidades permanecieron desconocidas: cobertura 0/36 y recobrado de ocurrencias 0/54. Tampoco se acreditó preservación del escenario constructivo (0/6). No existían referencias compatibles para coste, horas, recuperación o tiempo de técnicos. El informe no respalda una afirmación de ahorro ni cumplimiento completo de la transcripción. Detalles metodológicos en [EVALUACION_INTEGRAL](EVALUACION_INTEGRAL.md).

## Revisión y estado de entrega

Astra detectó y se corrigieron problemas que las pruebas iniciales no cubrían: contratos UI/API divergentes, cantidades hipotéticas materializadas como ocurrencias, revisiones sobrescritas, artefactos sin snapshot, trazas live omitidas, compatibilidad económica global incorrecta, analogías sin desglose que trasladaban materiales incompatibles y exclusiones de históricos eludibles mediante IDs explícitos. Cada cierre requiere la comprobación correspondiente; una revisión anterior no acepta automáticamente cambios posteriores.

Se han revisado los datasets de `1hack` y admitido dos fuentes económicas públicas adicionales: cuatro presupuestos académicos y quince coeficientes de tiempo de producción. Los precios de venta permanecen separados de los costes de fabricación. Véase [FUENTES_HISTORICO_PUBLICO](FUENTES_HISTORICO_PUBLICO.md).

Pendiente de cerrar este registro: integración final de artefactos y presentación, revisión de Astra sobre el árbol definitivo y despliegue con comprobación remota.

## Checkpoint de implementación antes de cierre

El usuario solicitó eliminar la revisión humana obligatoria y, posteriormente, ir guardando y subiendo los cambios. El incremento ahora incorpora propuesta multimodal, crítica con otro modelo, reparación semántica acotada, snapshots previos al crítico, derivados provisionales y estimaciones económicas condicionales por referencia. La edición humana es opcional. Las hipótesis mantienen su estado; la revisión automática no las convierte en hechos.

El primer checkpoint se verificó con 584 pruebas Python y 145 JavaScript aprobadas. El job HTTP real de la mesa propia terminó correctamente con GPT-6.1 Sol y GPT-6 Astra: una tapa y dos soportes como ocurrencias provisionales, sin confirmación humana. El primer auditor marcó un falso fallo al leer un nivel incorrecto del envelope SSE; se corrigió y la auditoría reanudada pasó 11/11 comprobaciones sobre el mismo job.

Los pilotos multimodales sobre casos diagnósticos revelaron defectos reales: tipos de comprobación indebidos expuestos al modelo, referencias con sintaxis ambigua y respuestas repetitivas. Se corrigieron restricciones y se compactó el contexto geométrico alrededor del 70 %. Después de un piloto que agotó 300 s, la versión v5 restringe al crítico a emitir decisiones sobre campos y comprobaciones. Los dos casos diagnósticos siguientes terminaron en 91,841 y 102,059 s, con abstenciones explícitas donde faltaba evidencia. El exportador de evaluación corregido en `208c5d6` excluye esas abstenciones de las predicciones respaldadas; el coordinador verificó sus 18 pruebas focales. La cohorte nueva de veinte entradas se ejecutó con esa versión congelada antes de abrir sus referencias privadas; los resultados se recogen más abajo.

Hay 19 registros públicos admitidos e importados en el servidor QA: cuatro presupuestos académicos con costes/horas y quince coeficientes de tiempo de producción. Procedencia publicada, naturaleza y alcance permanecen explícitos. La validación económica con un presupuesto retenido cada vez dio MAE 48,82 PLN y 0,46775 h sobre cuatro registros de una sola fuente. No es una medida de precisión empresarial.

Este commit es un checkpoint de desarrollo en la rama de trabajo, no una aceptación final ni un nuevo despliegue de producción.

El primer checkpoint se publicó como `c7ea203` en `feat/transcript-completion`, con comprobación conjunta propia de 584 pruebas Python y 145 JavaScript. Después se corrigió el lector del envelope SSE del auditor. La aceptación HTTP autónoma reanudada sobre el mismo job, sin nuevas llamadas pagadas, pasó 11/11 comprobaciones: Sol y Astra reales, tres imágenes de origen, tres ocurrencias provisionales, artefactos por snapshot y procedencia conservada. La estimación económica se abstuvo correctamente por geometría provisional incompleta; ese recorrido concreto no acredita todavía una cifra económica de extremo a extremo.

Tras el cambio de contrato del crítico y las correcciones de interfaz, el coordinador ejecutó la suite completa: 596 pruebas Python en 90,23 s y 147 JavaScript, todas aprobadas. Permanecen dos avisos de deprecación externos. Estas cifras corresponden a este checkpoint; la corrección posterior del exportador y la evaluación reservada requerirán su propia comprobación.

Una segunda aceptación HTTP, en servidor aislado con el algoritmo v5, pasó 10/10 comprobaciones sobre un DXF diagnóstico público. Produjo tres ocurrencias provisionales, ninguna física, y cuatro escenarios económicos numéricos con las fuentes publicadas: costes de 285,68 / 238,89 / 140,01 / 242,38 PLN y tiempos de 3,5 / 2,5 / 3 / 2,5 horas. Son escenarios condicionales, no aciertos económicos medidos ni una cotización. El informe local es `.runtime/transcript-qa/v5-http/audit-plank-001.json`; el undécimo check de la auditoría anterior comprobaba específicamente la reanudación de un job ya terminado.

La revisión visual del commit exacto `208c5d6` comprobó fuente, esquema, descargas BOM y 19 registros publicados, sin errores de consola ni solicitudes fallidas. Detectó dos problemas de presentación: el badge de fuente al restaurar una ejecución y rótulos/ocurrencias provisionales recortados en SVG. Se corrigieron en el worktree aislado. La comprobación posterior conserva tres ocurrencias visibles, procedencia íntegra y contornos DXF en milímetros exactos; no dibuja rectángulos con medidas inventadas para ejes desconocidos.

## Evaluación pareada de veinte planos

El runner de `208c5d6` completó 19 de 20 ciclos y conservó las veinte propuestas iniciales. Un caso falló en el proveedor después de P1 y mantiene final vacío en el denominador. Antes de abrir referencias, el coordinador verificó los 192 archivos del manifiesto sin discrepancias. Su SHA-256 es `8022af9e835773321d399a9b1345329d9a2a48756638678171060896c3f3b2b2`.

| Métrica | Propuesta inicial | Salida del crítico |
|---|---:|---:|
| Tipos alineados / referencia agrupada | 109 / 115 | 99 / 115 |
| F1 de tipos | 0,948 | 0,884 |
| Cantidades comparables / tipos de referencia | 104 / 115 | 98 / 115 |
| Precisión de ocurrencias | 0,964 | 0,977 |
| Recobrado de ocurrencias | 0,882 | 0,836 |
| Campos dimensionales comparados / conocidos | 327 / 345 | 297 / 345 |
| Campos dentro de 1 mm / comparados | 317 / 327 | 287 / 297 |

La agrupación y alineación usan tripletas dimensionales sin orientación; la medición del error conserva los ejes largo/ancho/espesor. El MAE por campo fue 6,331 mm y 6,970 mm: intercambiar ejes puede conservar el tipo geométrico y seguir siendo un error de asignación. La precisión de ocurrencias sube y la cobertura baja. No se demuestra mejora global por el crítico ni mejora de reparación DXF: los 19 finales tuvieron cero reparaciones semánticas. La caída mezcla abstenciones y el fallo del proveedor. Los escenarios carecen de adjudicación semántica independiente; estos resultados no certifican montaje ni ahorro empresarial. Detalles y splits en [EVALUACION_INTEGRAL](EVALUACION_INTEGRAL.md).

## PDF raster y reparación real

La reproducción instrumentada identificó un error concreto: se anunciaban referencias documentales que el materializador no admitía. También se observó una vista inventada y una respuesta incompleta del proveedor. Se unificaron referencias cerradas entre P1, reparación y crítico; una página raster sin ledger mantiene vistas/bindings vacíos y dimensiones nulas. Los errores operativos conservan códigos, contadores y trazas acotadas sin cuerpos ni secretos.

El control PDF raster posterior completó el flujo HTTP real: Sol produjo P1; Astra detectó conflicto, reformuló P2 y emitió C2 con estado incompleto. Se conservaron cinco componentes y seis ocurrencias provisionales, todas las dimensiones desconocidas. La reparación cambió etiquetas, supuestos y campos desconocidos; no demuestra una mejora de precisión dimensional. El control es mecánico y prueba el recorrido raster, no exactitud de mobiliario. Informe local: `.worktrees/conditional-hours/.runtime/raster-fix-http-20261114/qa-report.json`.

Antes del cierre se detectó otra incoherencia: el evaluador excluía los valores no aceptados por el crítico, pero algunos derivados y la tabla conservaban los números originales sin su decisión de revisión. Se está alineando la proyección de BOM, planos, escena y tabla con las decisiones del crítico; la propuesta y la revisión originales permanecen inmutables para trazabilidad.
