# Comparativa de métodos para Vexplorer

Estado: protocolo propuesto, sin ejecuciones de inferencia. Desarrolla la comparación planteada por el usuario y la [revisión de investigación y datasets](INVESTIGACION_Y_DATASETS.md). El [piloto actual](PILOTO_DATASET.md) verifica preparación e integridad, no precisión de modelos.

## Pregunta experimental

Cuánto aportan las herramientas y el histórico a la calidad del despiece y al tiempo de corrección, manteniendo explícita la información disponible. Familia inicial propuesta: armarios/estanterías rectangulares de tableros; los casos mecánicos actuales verifican capacidades técnicas por separado.

| Variante | Información y capacidades | Comparación que permite |
|---|---|---|
| A: reglas | Extracción y reglas deterministas, sin LLM | Referencia técnica para medidas y abstención |
| B: modelo visual directo | Imágenes permitidas, unidades respaldadas y tarea; sin herramientas ni referencias | Capacidad del modelo con una entrada fija |
| C: modelo con herramientas | Mismo modelo e información que B, más herramientas de inspección/cálculo sobre esa entrada | Aporte del bucle de herramientas |
| D: herramientas más histórico | C y un índice permitido de casos anteriores, sin duplicados del caso evaluado | Aporte marginal de recuperación histórica |

Los cuatro métodos están pendientes de implementación/evaluación. D requiere histórico anotado y admisión del índice; si falta, informar «no evaluado», nunca inventar comparables ni una puntuación cero.

## Igualdad de información y diferencias de formato

Separar dos experimentos:

1. **Representación común:** B/C/D reciben exactamente los mismos renders y contexto legítimo; C solo deriva información de esa misma entrada. Si A necesita vector y no existe extractor determinista raster comparable, marcar A como no aplicable en esta pista.
2. **Flujo completo:** mismo documento fuente, con acceso de A/C/D a primitivas DXF y de B al render. Informar esa diferencia: mide la utilidad del sistema completo, no aísla el efecto de las herramientas.

No comparar reglas sobre coordenadas DXF exactas con visión sobre un PDF rasterizado y atribuir toda diferencia a razonamiento. Fijar renders, resolución, selección de vistas, unidades y hashes. Evaluar por separado vistas conocidas/desconocidas y entradas completas/empobrecidas. Ningún método recibe STEP, BOM, programa de forma ni el detalle reservado para puntuar.

## Congelación de datos y ejecución

- Separar por mueble/familia/proyecto antes de generar vistas y variantes; duplicados y revisiones no cruzan particiones ni entran como vecinos del caso de prueba.
- Una ejecución recibe solo su ZIP individual, con contexto nuevo y herramientas restringidas. El ZIP agregado es transporte y contiene variantes relacionadas.
- Registrar versión del modelo, prompt, extractor, índice y reglas; límites de tiempo/llamadas, parámetros y hashes de entrada/salida. Usar los presupuestos de PLAN.md como límites, no como mediciones.
- Comparar C y D con el mismo modelo y límites; registrar gasto real. Si un modelo no admite semillas reproducibles, declarar esa limitación y conservar cada repetición.
- Propuesta inicial: tres repeticiones por método estocástico y caso, sin elegir la mejor a posteriori. Fijar presupuesto concreto antes de lanzar llamadas; esta documentación no las ejecuta.
- Contratos de salida y herramientas siguen pendientes del acuerdo A/B y aviso C exigido por CLAUDE.md; este protocolo no cambia contratos/ ni declara ese acuerdo.

## Qué medir

| Dimensión | Medición y denominador |
|---|---|
| Extracción | Error absoluto por cota y aciertos dentro de tolerancia predefinida, solo en campos con referencia y unidad fiables |
| Identidad/despiece | Componentes propuestos y confirmados, falsos positivos, omisiones y cantidades; correspondencia independiente antes de calcular precisión/recobrado |
| Evidencia | Fracción de afirmaciones respaldadas y referencias correctas; hipótesis explícitas separadas de hechos |
| Abstención | Cobertura en campos resolubles y abstención correcta en los no identificables; penalizar tanto inventar como abstenerse siempre |
| Geometría | Coherencia dimensional y entre vistas, únicamente con premisas verificadas; ejecución de CAD y similitud no sustituyen identidad |
| Recuperación | Recall@k/relevancia sobre vecinos etiquetados, explicaciones de diferencias y tasa de duplicados excluidos |
| Economía | MAE de coste y horas, cobertura y error relativo solo con referencia válida; comparar analogía y modelos tabulares con atributos disponibles en el momento del presupuesto |
| Utilidad humana | Minutos y correcciones hasta ficha aceptable, con orden de métodos contrabalanceado y evaluación independiente de las etiquetas del método |
| Recursos | Tiempo total, llamadas, tokens y coste de ejecución observado, no estimado a partir de una tarifa no comprobada |

No usar una puntuación global para ocultar errores críticos. Cuando no hay una única construcción identificable, aceptar alternativas justificadas y evaluar preguntas pendientes; no penalizar la falta de conocimiento de una pieza oculta como si fuera una cota visible omitida. Publicar tamaños de muestra, campos sin referencia, fallos y resultados por familia.

## Aplicación al piloto existente

- Los 14 DXF son pruebas de extracción de piezas individuales con anotaciones, no 14 problemas de despiece desde un plano pobre.
- visual-001 permite valorar propuestas y reconocimiento de incertidumbre, pero una vista sin cotas no identifica de forma única la BOM completa.
- visual-002 controla lectura de dimensiones; visual-003 exige conservar desconocidos el espesor y la cantidad. Ejecutarlos en contextos separados.
- Todos son casos de desarrollo ya inspeccionados. Para afirmar generalización hacen falta casos reservados que no se hayan usado para ajustar prompts/reglas.
- El histórico económico no está en este piloto. La fase de costes requiere datos adicionales; una prueba con tarifas sintéticas solo valida aritmética.

## Criterio de continuidad

Escoger el método que reduzca trabajo humano manteniendo los errores y la cobertura acordados con el técnico; no el que produzca más piezas ni el render más atractivo. Conservar A como baseline aunque C/D resulten mejores. Integrar un corpus de mobiliario si aporta pares verificables y un campo de evaluación que hoy falta, no simplemente más volumen.
