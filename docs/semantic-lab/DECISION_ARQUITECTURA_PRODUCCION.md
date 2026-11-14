# Decisión de arquitectura para búsqueda y clasificación de mobiliario

Fecha: **2026-11-14**. Estado: **dirección de arquitectura aceptada por el usuario; validación operativa e implementación productiva pendientes**. Evidencia de partida: laboratorio publicado en el commit `14a6514ddd82e8914aa128ff5787d029517a3f3f`.

El usuario aprobó documentar esta decisión y su [diseño técnico](DISENO_ARQUITECTURA_PRODUCCION.md), publicarlos en GitHub e integrar la rama del laboratorio en `main`. La integración incorpora investigación, herramientas, pruebas y diseño; no activa por sí misma un servicio de Gemma o Jev en la aplicación desplegada.

## 1. Decisión

Adoptar una arquitectura con responsabilidades separadas:

| Responsabilidad | Elección | Condición de uso |
|---|---|---|
| Representación y búsqueda de planos similares | **EmbeddingGemma 2 mixto, 768 dimensiones, normalización L2 y sin PCA**; similitud coseno | Mantener una identidad de espacio vectorial completa y el mismo preprocesado entre catálogo y consulta. |
| Clasificación de familias | **Regresión logística sobre embedding y geometría** como candidato principal para una taxonomía amplia | Entrenar y seleccionar con un corpus propio revisado; conservar kNN como control. La elección no congela las categorías editoriales ni un checkpoint experimental para producción. |
| Revisión semántica adicional | **Jev visual opcional**, con salida estructurada, abstención y presupuesto | Sus sugerencias requieren la política de revisión del producto; no validan medidas ni cantidades. |
| Similitud constructiva | Medidas, materiales, componentes, cantidades y operaciones respaldados por evidencia | Se incorpora como segunda comparación explicable, con cobertura de campos conocidos; debe evaluarse con relevancia técnica humana. |
| Comparables de coste y tiempo | Histórico revisado y ajuste económico determinista | La semejanza visual no basta para admitir un comparable de precio. |

La primera entrega funcional debe ser un piloto de búsqueda y clasificación asistida. La automatización de etiquetas y la estimación económica tienen criterios de aceptación independientes.

## 2. Qué son PCA y Gemma en esta decisión

**EmbeddingGemma** es el modelo que transforma el contenido de entrada en un vector. En el experimento se codificó conjuntamente un render geométrico del plano y un texto con seis observaciones geométricas globales. Se probaron 768 y 256 dimensiones. No se midió todavía el beneficio de alimentar el descriptor completo del harness o una BOM revisada.

**PCA** es una transformación estadística posterior que proyecta vectores en menos dimensiones, conservando tanta variación como permite la proyección. No es un modelo de interpretación de planos ni un clasificador. La variación conservada tampoco garantiza conservar las diferencias semánticas o constructivas importantes.

No son alternativas del mismo nivel: puede usarse Gemma y después PCA. Aquí se elige **no comprimir con PCA** porque el criterio de selección del experimento favoreció la representación sin esa transformación. Esto no demuestra que PCA sea siempre perjudicial. Una futura compresión exigiría una comparación de relevancia, memoria y latencia; se ajustaría sólo sobre train y produciría una versión de índice distinta. Una proyección 2D para visualizar grupos no sustituye el vector de recuperación.

## 3. Evidencia que sustenta la elección

| Método de clasificación cerrada | Core: macro-F1, 18 casos test | CAD adicional: macro-F1, 55 casos test |
|---|---:|---:|
| EG2 mixto 768 + kNN5 | 0,8261 | 0,7780 |
| Mejor clasificador local seleccionado por validation | 0,8261, kNN | **0,8445, regresión logística** |
| Jev 1.14, imagen + texto geométrico | **0,9143** | 0,5249 |

Fuentes: [resultado inicial](../SEMANTIC_LAB_2026-11-14.md), [clasificadores locales](COMPARACION_CLASIFICADORES_LOCALES.md), [Jev](COMPARACION_JEV.md) y [pruebas adicionales](PRUEBA_EMBEDDINGS_OTROS_DATASETS.md).

- La búsqueda inicial seleccionó EG2 mixto 768 + kNN5, sin PCA, entre 228 configuraciones usando validation. El test original obtuvo Precision@5 de 0,8889. En CAD adicional, el mismo espacio y método alcanzaron Precision@5 de 0,7745.
- Para la clasificación amplia, la logística seleccionada usó `StandardScaler` sobre la concatenación de 768 dimensiones y 27 características geométricas, `class_weight="balanced"` y `C=0.1`. Tanto escalado como clasificador se ajustaron exclusivamente con train. Es una configuración inicial para reevaluar, no una constante productiva garantizada.
- En el conjunto pequeño ganó el control kNN frente a los otros clasificadores locales. No se afirma que logística gane en todas las taxonomías.
- Jev funcionó por API con 320 respuestas válidas, pero su ventaja en core no se mantuvo en las categorías adicionales. La combinación de Gemma, logística y revisión Jev **no se ha evaluado como una cascada de extremo a extremo**.
- En el control mecánico, la pregunta abierta de Jev visual se abstuvo en 13/14 casos. Esto no calibra un detector general de entradas desconocidas.

El test inicial se abrió después de congelar la selección. Las comparaciones posteriores de Jev y clasificadores reutilizaron particiones ya observadas y son **retrospectivas**. Las etiquetas son categorías editoriales, con mezclas y ruido; no constituyen una taxonomía industrial revisada. Las diferencias anteriores no prueban superioridad universal ni justifican promesas comerciales de precisión.

## 4. Alternativas consideradas

| Alternativa | Aportación | Motivo para no adoptarla como arquitectura principal |
|---|---|---|
| Geometría sola | Económica, determinista y explicable | Pierde información visual útil y no fue el ganador de la selección inicial. Se conserva como señal y control. |
| Gemma + kNN para todo | Recuperación y clasificación sencillas con un único espacio | Es un buen control, pero la logística mejoró la clasificación amplia; ambos necesitan resolver abstención y taxonomía. |
| Jev como clasificador único | Buen resultado en core y capacidad de respuesta abierta | Bajó en CAD adicional, añade dependencia de API y no proporciona el índice vectorial de búsqueda. |
| PCA antes de recuperar o clasificar | Menos memoria y cálculo potenciales | No mejoró la selección del experimento; no se ha demostrado una necesidad operativa que compense la pérdida de información. |
| Clustering como catálogo definitivo | Puede ayudar a explorar y descubrir grupos | La prueba fue transductiva y elegida con etiquetas de validation; no demuestra asignación automática fiable de nuevas entradas. |
| Gemma para búsqueda + clasificador local + revisión opcional | Permite mejorar clasificación, recuperación y revisión por separado | **Elegida**. Requiere versionar cada componente y medir el recorrido integrado. |

Se conservan las alternativas como baselines de evaluación. No se mantienen varios encoders en cada petición por defecto: añadir modalidades o modelos requiere demostrar su beneficio frente al coste operativo.

## 5. Consecuencias de diseño

1. **Recuperación y etiqueta se desacoplan.** Cambiar el clasificador no cambia por sí solo los vecinos de Gemma. Una categoría propuesta no debe filtrar rígidamente todos los candidatos y ocultar un vecino válido por un error de clasificación.
2. **El vector no es una medida física.** El preprocesado experimental conserva proporciones y elimina escala absoluta. Dimensiones, unidades, material y espesor proceden del ledger y de datos revisados; nunca se reconstruyen del coseno.
3. **Se mantiene la unidad documental.** Varias vistas no multiplican piezas; un documento con varios muebles no se presenta automáticamente como un único objeto físico. La asociación de objetos y vistas requiere evidencia o revisión.
4. **Las hipótesis conservan su estado.** Etiqueta propuesta, pieza confirmada, observación y ocurrencia física son conceptos distintos. Falta de evidencia conduce a revisión; no se completa con valores típicos.
5. **El índice es un artefacto versionado.** Modelo/revisión, modalidad, renderizador, texto, dimensión, normalización y esquema de características identifican su espacio. Una migración construye un índice separado; no mezcla espacios OpenAI y Gemma.
6. **La calidad de entrada tiene prioridad.** El laboratorio excluyó seis CAD adicionales y la prueba offline de la app admitió 53 archivos sin producir piezas ni propuestas generales. Integrar un encoder no corrige esos límites del harness.
7. **El histórico económico es otra frontera.** Recuperar una mesa parecida no demuestra igual material, mecanizado, acabado, transporte, moneda, fecha o coste de preparación. La ficha debe explicar coincidencias, diferencias y datos ausentes.

## 6. Condiciones para activar producción

Estos son requisitos de evaluación y operación del diseño. Sus valores numéricos se deben fijar **antes de abrir el nuevo test**, con los responsables del producto, según el coste del error y la carga de revisión. No se inventan umbrales de aprobación a partir de los resultados ya vistos.

| Frontera | Evidencia necesaria |
|---|---|
| Corpus y taxonomía | Planos propios o autorizados con revisión técnica, familias coherentes y particiones por objeto/proyecto/fabricante; vistas y revisiones relacionadas permanecen juntas. |
| Clasificación | Macro-F1, balanced accuracy, errores por familia y cobertura; comparación con kNN y geometría. Calibración y umbrales elegidos con validation independiente. |
| Recuperación | Relevancia humana de vecinos, Precision@k/Hit@k, cobertura y fallos; medir también consultas con cambios de vista y documentos con varios objetos. |
| Abstención | Casos desconocidos y entradas inválidas independientes; medir falsa aceptación y revisión necesaria. Una probabilidad máxima o un coseno alto no bastan. |
| Extracción y construcción | Medidas, asociaciones, cantidades y componentes contrastados con referencias; campos desconocidos conservados y trazabilidad verificable. |
| Precios y horas | Histórico emparejado con planos, procedencia, fechas, unidades y alcance económico; errores de estimación y cobertura evaluados aparte. |
| Operación | Medición de latencia, memoria, cola y coste bajo carga representativa; límites de API, aislamiento de catálogos, invalidación de revisiones y recuperación comprobados. |
| Promoción y reversión | Ejecución en sombra, piloto revisado, activación gradual y rollback del conjunto de modelo/índice/política; resultados revisados conservan su procedencia. |

La debilidad entre vistas observada en Plank (Hit@1 de 0,30 para 10 objetos/30 vistas) debe formar parte del siguiente corpus. No se elimina seleccionando sólo consultas visualmente fáciles.

## 7. Alcance de la integración y seguimiento

La decisión fija el rumbo técnico; el [diseño](DISENO_ARQUITECTURA_PRODUCCION.md) concreta componentes, datos, transiciones, despliegue gradual y verificación. Los cambios futuros de contratos deben seguir el acuerdo A/B y aviso C definidos en [CLAUDE.md](../../CLAUDE.md), usando Pydantic como única fuente de verdad.

El código del laboratorio permanece reproducible y separado del runtime. Integrarlo en `main` permite trabajar sobre evidencia compartida; no convierte los NPZ y clasificadores del experimento en modelos productivos ni despliega nuevos endpoints. El siguiente incremento implementable es la ingesta semántica versionada y la búsqueda en sombra, seguido por clasificación y revisión medidas sobre el corpus propio.

Esta decisión se revisará si el nuevo holdout, la relevancia humana, los requisitos de privacidad o las mediciones operativas favorecen otra representación. Cambiar de decisión requerirá conservar el benchmark anterior y explicar el resultado nuevo, no reinterpretar retroactivamente estos ensayos.
