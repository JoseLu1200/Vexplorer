# Completar muebles desde vistas CAD 2D

## Encargo vigente

El usuario precisa el objetivo: partir de vistas 2D de un mueble completo con pocas cotas, interpretar su construcción, deducir o estimar medidas y detalles faltantes, proponer las piezas necesarias y entregar sus planos acotados. La aplicación debe explicar las decisiones y partes importantes. Una salida que conserva todos los faltantes como desconocidos no satisface este encargo.

Base de implementación: `0e65713`; worktree `.worktrees/cad-completion`, rama `feat/cad-completion`. Se conserva el trabajo anterior como checkpoint. Esta fase se concentra en CAD 2D, construcción y planos de piezas.

## Resultado principal

Un único resultado constructivo provisional alimenta el resumen del mueble, la lista de piezas y sus planos. Las dimensiones estimadas aceptadas por la revisión automática **se incluyen como números** en la lista y en los planos de propuesta, con nominal, rango, fundamento y marca de estimación. No se relegan a un informe lateral mientras la lista permanece vacía.

Las observaciones del CAD permanecen inmutables. Se distinguen tres bases de dimensión: observada, deducida mediante operación comprobable y estimada como decisión de construcción. Una deducción dependiente de una estimación conserva esa dependencia y su incertidumbre; cerrar una ecuación no la convierte en observación. No se requieren aprobaciones humanas para obtener la propuesta.

## Construcción y coherencia

- El modelo propone un escenario principal: parámetros, piezas visibles o necesarias, cantidades, forma local explícita, relaciones de montaje y detalles relevantes.
- Un parámetro estimado tiene nominal, intervalo plausible, método, premisa y explicación breve. El intervalo no se presenta como probabilidad calibrada.
- Las operaciones referenciadas se evalúan en el servidor; las cotas globales, sumas de espesores, vanos, repeticiones y encajes se comprueban con restricciones explícitas.
- Las cantidades corresponden a piezas del escenario, nunca al número de vistas.
- La crítica multimodal juzga coherencia y plausibilidad de las estimaciones declaradas. La ausencia de una cota observada no es por sí sola motivo para rechazar una estimación bien fundamentada.
- Las contradicciones con cotas observadas disparan reparación automática. Se conserva el diagnóstico y la propuesta anterior.
- Las alternativas incompatibles se explican; no se mezclan sus piezas en una misma lista.

## Planos y explicación

Cada tipo de pieza propuesto tiene una lámina 2D con vistas pertinentes, contorno explícito, largo/ancho/espesor, cantidad, cotas gráficas y detalles constructivos disponibles. Los parámetros estimados también definen geometría de propuesta en mm, marcada como tal. SVG y DXF distinguen observado, deducido y estimado mediante estilo y texto.

El conjunto 2D representa posiciones propuestas cuando están definidas; su condición de propuesta queda explícita. Los planos por pieza no dependen de completar un montaje 3D. No se inventa un contorno desde un bounding box: el modelo debe proponer la forma y su fundamento.

La interfaz prioriza construcción, piezas y planos. Al seleccionar una pieza se ven sus cotas, fórmulas, rangos, fuentes y decisiones. Se destacan pocas decisiones de alto impacto, por ejemplo espesor elegido, panel oculto necesario, holgura de un cajón o alternativa de unión.

## Aceptación

Tres casos propios iniciales: mesa con faldón, estantería y cajonera/armario. Cada entrada contiene vistas montadas y cotas escasas, sin BOM ni respuestas. Las referencias separadas admiten alternativas coherentes y rangos para lo que realmente no puede deducirse.

El cierre exige ejecutar el harness real, inspeccionar visualmente los planos resultantes, comprobar ecuaciones y cantidades y obtener un plano útil por pieza. No se presentará solo un recuento de tests como cumplimiento. Los ejemplos son controles funcionales, no una certificación de rendimiento industrial.

## Propiedad

- Backend general: contrato Pydantic único, parámetros, materialización, herramientas/prompt de propuesta e integración de derivados.
- Consistencia (agente economy): `construction_validation.py` y pruebas deterministas.
- Planos (agente ingestion): planner/renderer de conjunto y piezas, cotas/detalles y sus pruebas.
- Integración: persistencia, router, main, snapshots, eventos, `review.py` y crítica/reparación en `autonomous.py` (transferencia confirmada antes de editar).
- Interfaz: presentación 2D, selección de piezas, explicación y descargas.
- Evaluación: fixtures propios y comprobación independiente de utilidad constructiva.
- Coordinación: integración, ejecución real, inspección visual, commits y documentación.
- Astra: revisión del contrato y del comportamiento final.
