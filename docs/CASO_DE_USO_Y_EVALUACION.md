# Caso de uso y evaluación de la prueba de concepto

**Fuente de requisitos:** [transcripción original](../transcripcion-contexto-poc.md), conservada literalmente. Este documento ajusta el alcance del paquete del hackathon a esa necesidad. Es un plan pendiente de implementación y evaluación, no una declaración de capacidades existentes.

## Qué necesita la empresa

Un equipo de unas 50 personas interpreta planos CAD poco informativos del mueble terminado. Debe deducir piezas, secciones, medidas y cantidades para que compras y administración puedan estimar materiales, tiempo y presupuesto. Además, busca muebles anteriores parecidos para presupuestar nuevos encargos según diferencias de dimensiones, materiales y acabados.

La entrada principal son vistas 2D de líneas y cotas, preferentemente DXF y DWG. Un modelo 3D, un bloque arquitectónico del mueble completo o una BOM ya escrita no demuestran por sí solos esa capacidad. El visor 3D es opcional y secundario.

| Necesidad de la transcripción | Entrega prevista | Evidencia para evaluarla |
|---|---|---|
| Interpretar un plano pobre del mueble final | Propuesta de componentes y secciones con alternativas, cantidades y dudas | Plano de entrada separado del despiece de referencia |
| Obtener información para compras | Tabla de piezas, dimensiones, material, acabado, unidades y campos pendientes | Revisión técnica independiente y enlace a observaciones o supuestos |
| Evitar una demostración trivial | Evaluación con respuesta oculta y eliminación controlada de información | Manifiesto de transformaciones y auditoría de fugas |
| Encontrar muebles anteriores parecidos | Lista ordenada de comparables y diferencias explicadas | Histórico separado del caso de prueba y relevancia anotada |
| Orientar tiempo y presupuesto | Estimación provisional con cálculos, procedencia y revisión | Costes/tiempos históricos reales o fixtures claramente sintéticos |

## Dos hitos, sin confundir sus resultados

**Hito técnico P0 (T1–T10):** extracción geométrica, cotas, referencias, identidad, revisión básica y exportación. Orla y los fixtures propios sirven aquí. Los contratos 0.1.0 y sus ejemplos describen este hito; todavía no representan descomposiciones nuevas de un mueble ni presupuestos.

**Prueba de concepto de negocio (T11–T13, obligatorias para el objetivo):** proponer componentes desde información incompleta, recuperar muebles históricos y calcular una estimación revisable. Depende del hito técnico y de conseguir referencias de mobiliario adecuadas. No se sustituye por abrir un DXF, mostrar cajas o extraer una BOM visible. Si falta un corpus real, se puede mostrar una demostración sintética, rotulada como tal, y declarar pendiente la validación en mobiliario real.

Los contratos adicionales requieren el acuerdo de equipo establecido en CLAUDE.md antes de implementar. Esta actualización define requisitos y tareas; no declara aprobados campos, endpoints ni herramientas nuevas.

## Corpus emparejado y eliminación de pistas

Para cada mueble, conservar por separado:

- **Entrada permitida:** plano original pobre o versión empobrecida de vistas del mueble terminado, con las cotas generales que realmente tendría el técnico.
- **Referencia reservada al evaluador:** planos de detalle, despiece, secciones, BOM, cantidades, materiales, acabados y medidas revisadas por una persona competente. Marcar como desconocido cualquier campo sin referencia fiable.
- **Manifiesto:** identificador de familia/proyecto, procedencia, licencia, hashes, unidades y transformaciones; ubicación de la referencia fuera del directorio accesible al agente. No enviar el manifiesto privado ni su contenido revelador en el prompt.

Si solo hay planos completos, producir variantes controladas: eliminar BOM, globos de referencia, nombres de piezas, tablas de corte y detalles que ya resuelvan el despiece. Revisar también capas ocultas, bloques y atributos, textos, layouts, nombres de archivo, metadatos, miniaturas y sidecars. No basta con ocultarlos en el visor: deben quedar fuera de los bytes y herramientas de entrada. Mantener unidades y cotas generales útiles; registrar exactamente qué se retiró. Una entrada completamente indeterminada debe admitir varias soluciones y preguntas pendientes.

Comparar por separado plano completo, plano empobrecido y plano pobre real. La ablación artificial no representa automáticamente la distribución de planos recibidos en la empresa. No borrar una cota visible y dejar su respuesta en un JSON accesible al agente.

Separar desarrollo, prueba e histórico por familia de mueble/proyecto antes de generar variantes. Agrupar duplicados, revisiones, escalados y sus derivados para que no crucen particiones. Un caso de prueba no puede recuperar su propio despiece del índice. Congelar la selección y la referencia antes de evaluar.

El dataset mecánico es auxiliar para lectura de CAD y asociación de detalles. [PlankAssembly](PLANKASSEMBLY.md) ya está descargado y aporta componentes de mobiliario en forma paramétrica, con unidades mm. Sus entradas 2D aún deben generarse y revisarse. Permitirá evaluar pares controlados; la utilidad empresarial sigue requiriendo planos pobres reales, revisión humana e histórico de costes.

## Inferir sin presentar supuestos como hechos

Separar cuatro clases de información en pantalla y exportaciones:

| Clase | Ejemplo | Tratamiento |
|---|---|---|
| Observada | Cota exterior de 600 mm | Referencia a entidad/cota y unidades |
| Derivada | Ancho calculado a partir de dimensiones y montaje respaldados | Operación determinista y referencias de todas las premisas |
| Hipótesis | Dos laterales y una balda; espesor supuesto para comparar escenarios | Alternativa explícita, motivo, incertidumbre y revisión pendiente |
| Confirmada por técnico | Material o disposición aportados por una persona | Autor, fecha, fuente y revisión nueva; no convertirlo en observación del CAD |

Permitir que el agente proponga piezas o secciones que no estén dibujadas individualmente: asociarlas a regiones/vistas de origen y explicar qué construcción las justificaría. La falta de un contorno de pieza explícito no impide registrar una propuesta, pero impide publicarla como pieza medida y validada. Hipótesis incompatibles son escenarios separados, nunca cantidades sumadas.

El agente no escribe cifras arbitrarias en el libro geométrico. Un valor supuesto, si se necesita para presupuestar un escenario, procede de una decisión humana o regla identificada, queda fuera de las medidas observadas y lleva estado provisional. Las operaciones se ejecutan con código y premisas declaradas. Un nombre como «balda» no demuestra una unión, un espesor ni una resta válida. No inventar una probabilidad calibrada a partir de la confianza verbal del modelo.

La revisión debe poder aceptar, rechazar, dividir o unir componentes propuestos y aportar evidencia de montaje, cantidad o material. Registrar autor y motivo; regenerar el libro y su fingerprint cuando cambien premisas. El endpoint de revisión 0.1.0 no tiene todavía esa capacidad: T11 debe ampliarlo de forma versionada, sin reinterpretar silenciosamente sus campos.

## Histórico y estimación

Construir un catálogo de proyectos anteriores con identificador, familia, dimensiones y unidades, componentes disponibles, material, acabado, fecha y fuente. Coste y tiempo pueden faltar; distinguir presupuesto de coste real y horas de trabajo de plazo de entrega. Registrar moneda, fecha, alcance incluido y cantidades. Datos inventados solo como fixtures rotulados.

Comparar una baseline de filtros y distancias normalizadas sobre dimensiones/material/acabado con recuperación mediante embeddings del contenido permitido. Guardar versión del modelo, índice, normalización y pesos. Ningún embedding acredita medidas o equivalencia de fabricación. Mostrar los comparables con sus diferencias concretas y campos ausentes; una similitud global no basta para justificar precio.

Calcular costes por conceptos comparables cuando el histórico los permita. Para cada concepto, la propuesta es `coste_nuevo = coste_base × factor_cantidad × factor_consumo × factor_precio_unitario`, con factores documentados, unidades compatibles y sin doble contabilización. Usar área, longitud o volumen según el concepto; no multiplicar todo el precio por una razón de anchos. Separar costes fijos, material, mecanizado, mano de obra, acabado y margen cuando estén disponibles. Cambios de material o acabado requieren tarifas o supuestos explícitos, no factores fabricados por el LLM.

Estimar horas con su propio modelo de operaciones, preparación y cantidades; no convertir euros a horas sin una tarifa justificada. Sin desglose suficiente, presentar analogía global de baja evidencia o abstenerse de dar importe. Las bandas son escenarios mínimo/base/máximo sustentados, no intervalos estadísticos inventados. Sin comparables válidos, indicar datos necesarios para estimar.

Entregar a compras/administración una ficha con piezas y estados, comparables usados, cálculo por conceptos, supuestos, exclusiones, moneda/fecha, horas y pendientes de revisión. Es una estimación provisional, no una orden de compra ni un presupuesto aprobado.

## Evaluación y criterios de aceptación

Comenzar con armarios/estanterías de tableros y un reservado independiente de desarrollo; para ampliar cobertura, seleccionar después al menos tres familias con referencias revisadas; informar el número real de casos y no generalizar desde esa muestra pequeña. Si no es viable, reducir la demostración y declarar qué objetivo no se ha validado. Acordar tolerancias y criterios antes de observar resultados; no afinarlos sobre el conjunto reservado.

| Prueba | Qué registrar |
|---|---|
| Extracción con evidencia | Error dimensional con unidad/tolerancia declaradas; cobertura y abstenciones |
| Inferencia desde plano pobre | Precisión/recobrado de componentes, cantidad, secciones y medidas; hipótesis falsas y correcciones humanas |
| Ambigüedad | Varias soluciones plausibles preservadas, sin asumir que el despiece de referencia es la única construcción posible |
| Fugas de respuesta | Entradas, herramientas, índice y trazas sin acceso a referencias reservadas ni duplicados del caso |
| Recuperación histórica | Relevancia top-k valorada por técnico, Recall@k sobre conjunto etiquetado y comparación de baseline frente a embeddings |
| Estimación | Error absoluto y relativo de coste y horas donde haya verdad de referencia; cobertura y motivos de abstención |
| Utilidad operativa | Tiempo y correcciones hasta una ficha aceptable frente a lectura manual de casos comparables |

Comparar reglas geométricas solas, harness con esas mismas entradas y revisión humana; mantener idéntica información permitida. Separar resultados reales de sintéticos y planos completos de empobrecidos. No calcular error relativo cuando el valor de referencia sea cero o desconocido.

La demo de negocio debe enseñar entrada pobre → propuestas de despiece → revisión → comparables → estimación explicada. Revelar el despiece reservado solo después de congelar el resultado evaluado. La aprobación técnica y cualquier uso para fabricación quedan en manos de la persona responsable.
