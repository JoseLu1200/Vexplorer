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

El usuario ha pedido además revisar todos los datasets de `1hack` y descargar fuentes adicionales cuando resulten útiles. La auditoría local y la búsqueda de fuentes económicas públicas están en curso. No se sustituirán costes/horas de fabricación por precios de venta sin identificar ese alcance.

Pendiente de cerrar este registro: revisión final de Astra sobre árbol definitivo, prueba final de interfaz económica, fuentes adicionales admitidas y despliegue con comprobación remota.

## Checkpoint de implementación antes de cierre

El usuario solicitó eliminar la revisión humana obligatoria y, posteriormente, ir guardando y subiendo los cambios. El incremento ahora incorpora propuesta multimodal, crítica con otro modelo, reparación semántica acotada, snapshots previos al crítico, derivados provisionales y estimaciones económicas condicionales por referencia. La edición humana es opcional. Las hipótesis mantienen su estado; la revisión automática no las convierte en hechos.

La comprobación independiente más reciente de Astra obtuvo 584 pruebas Python y 145 JavaScript aprobadas. El job HTTP real de la mesa propia terminó correctamente con GPT-6.1 Sol y GPT-6 Astra: una tapa y dos soportes como ocurrencias provisionales, sin confirmación humana. El primer auditor marcó un falso fallo al leer un nivel incorrecto del envelope SSE; la corrección y la verificación del resto de artefactos siguen pendientes.

Los pilotos multimodales sobre casos diagnósticos revelaron defectos reales: tipos de comprobación indebidos expuestos al modelo, referencias con sintaxis ambigua y respuestas repetitivas. Se corrigieron restricciones y se compactó el contexto geométrico alrededor del 70 %. El último piloto complejo aún agotó el plazo de 300 s durante el ciclo de reparación; no se presenta como un caso aceptado. La cohorte nueva de veinte entradas está preparada y todavía no evaluada.

Hay 19 registros públicos admitidos e importados en el servidor QA: cuatro presupuestos académicos con costes/horas y quince coeficientes de tiempo de producción. Procedencia publicada, naturaleza y alcance permanecen explícitos. La validación económica con un presupuesto retenido cada vez dio MAE 48,82 PLN y 0,46775 h sobre cuatro registros de una sola fuente. No es una medida de precisión empresarial.

Este commit es un checkpoint de desarrollo en la rama de trabajo, no una aceptación final ni un nuevo despliegue de producción.

El primer checkpoint se publicó como `c7ea203` en `feat/transcript-completion`, con comprobación conjunta propia de 584 pruebas Python y 145 JavaScript. Después se corrigió el lector del envelope SSE del auditor. La aceptación HTTP autónoma reanudada sobre el mismo job, sin nuevas llamadas pagadas, pasó 11/11 comprobaciones: Sol y Astra reales, tres imágenes de origen, tres ocurrencias provisionales, artefactos por snapshot y procedencia conservada. La estimación económica se abstuvo correctamente por geometría provisional incompleta; ese recorrido concreto no acredita todavía una cifra económica de extremo a extremo.
