# Mesa: vistas montadas, propuesta y planos derivados

Estado: diseño de la siguiente ampliación, aún no implementada. El hito 0.4 de piezas separadas está publicado en main `164356b`, con SHIP de Astra. El usuario pide acabar ese hito y continuar desde vistas 2D de un mueble montado con cotas parciales hasta despiece, planos acotados por pieza y costes explicados.

## Recorrido y alcance

Caso propio inicial: mesa rectangular de tablero superior y soportes sencillos, dibujada en DXF con planta, alzado y perfil. Sin modelo 3D de entrada ni BOM para el agente. Se mantienen los dos modos de entrada existentes y se añade explícitamente `mounted_orthographic_views`, perfil `rectangular_table_v1`.

El recorrido nuevo será: DXF fuente y cotas parciales → medidas/evidencias → propuesta de componentes y asignación de medidas → revisión humana versionada → plano general derivado acotado → planos por tipo de pieza y distribución de despiece con cotas → reconstrucción esquemática y costes por pieza/concepto → exportaciones.

Las cotas que falten pueden obtenerse de geometría métrica o de operaciones justificadas. La asignación semántica de una medida a una pieza puede seguir siendo hipótesis. Un valor sin base admitida permanece desconocido. Ningún plano se presenta como validado para fabricación, resistencia o uniones.

## Modelo generativo acotado

El modo live incorpora una herramienta de propuesta que permite al modelo construir un programa de componentes, roles, referencias y reglas; no se limita a elegir una BOM precalculada. El servidor calcula las cifras. No se aceptan floats, expresiones ejecutables, coordenadas ni cantidades arbitrarias del modelo.

Programa declarativo limitado: bindings en orden con operaciones `copy`, `add`, `subtract`, operandos referidos a medidas permitidas o bindings anteriores; componentes con rol, bindings de largo/ancho/espesor y reglas de cantidad/colocación versionadas. Se admiten límites pequeños de componentes y bindings, sin ciclos, referencias futuras o valores no finitos. Cada componente debe tener evidencia de entrada o una regla de diseño explícita.

Reglas iniciales: tablero superior único, dos soportes laterales o cuatro soportes de esquina, con requisitos geométricos documentados. La regla puede proponer cantidad/colocación, pero no demostrar que ésa sea la construcción original. No se codifica la respuesta del fixture en extractor o prompt. Una regla incompatible con la geometría disponible se rechaza o mantiene incompleta, sin descartar silenciosamente evidencia contradictoria.

`geometry_only` sigue siendo utilizable sin proveedor: ledger y planos fuente; una propuesta de catálogo seleccionada explícitamente se etiqueta `catalog_baseline`. No se anuncia como inferencia de modelo. Live se etiqueta como modelo real y conserva herramientas/propuesta validada en la traza. Replay permanece deshabilitado.

## Revisión y dependencias

Una única definición Pydantic, propiedad de B. Estados distinguen observado, calculado, propuesto, confirmado, desconocido y conflicto. Aritmética sobre una propuesta continúa siendo propuesta hasta su aceptación. Se conservan fuentes y dependencias estructuradas, regla/versionado y hash del programa.

La persona puede aceptar/rechazar componentes, confirmar supuestos o aportar medidas que faltan. Cambiar un dato humano recalcula medidas, planos, escena y costes dependientes en otra revisión. Una operación no puede cambiar una observación existente ni ocultar una contradicción. Las revisiones anteriores permanecen recuperables y las peticiones obsoletas se rechazan.

## Planos y estimación

SVG y DXF derivados comparten revisión y hash del programa. Se conserva separado el DXF original. Capas/leyenda y cotas distinguen procedencias; toda propuesta sin confirmar se marca como hipótesis. Las medidas desconocidas se muestran como tales; no se simulan cotas completas. Salidas: conjunto ortográfico acotado, detalle por tipo de pieza con cantidad y dimensiones, y hoja de despiece acotada.

El coste muestra contribución por pieza y concepto, con tarifas sintéticas explícitas y sin duplicar preparación. Material por área o volumen con unidad correcta; canto por longitud cuando el alcance está seleccionado; operaciones, horas y acabados sin base permanecen desconocidos. El total conocido es provisional y no equivale a precio de venta. Que el tablero mayor aporte más coste se demuestra con las cifras del caso, no se impone como regla universal.

Se integra en biblioteca/descriptor con familia y perfil de piezas coherentes. La similitud no determina un precio. No se añaden proveedores o infraestructuras nuevas si el stack actual basta.

## Aceptación

- Caso completo y variante incompleta propios; referencia sólo para D después de congelar salidas.
- Misma entrada sin montaje 3D, familia/perfil explícitos y variación de dimensiones: sin respuesta prefijada.
- Modelo real entrega un programa válido mediante herramientas; referencias falsas/ciclos/números arbitrarios/contradicciones rechazados.
- Planos general, piezas y despiece muestran cotas efectivas; DXF exportado vuelve a abrirse con unidades y entidades correctas.
- Revisión recalcula dependencias y conserva historial; desconocidos no se convierten en cifras sin decisión.
- Coste por piezas/conceptos explicado y comprobado independientemente, sin doble conteo.
- API y navegador reales, pruebas significativas, README, informe de límites, revisión final Astra, integración y push main autorizados.
