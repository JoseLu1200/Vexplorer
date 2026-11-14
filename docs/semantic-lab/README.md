# Laboratorio semántico de mobiliario

Fecha de la investigación inicial: **2026-11-14**. Rama: `experiment/semantic-furniture`. Base del experimento: `4209510`. Este directorio organiza la auditoría, investigación, código experimental, resultados y límites del trabajo solicitado sobre embeddings, clasificación, búsqueda de similares y su posible uso económico.

## Qué se obtuvo

Un laboratorio CLI reproducible y un índice consultable de planos DXF. En el experimento inicial con 117 planos, el método seleccionado fue **EmbeddingGemma 2, imagen más observaciones geométricas, 768 dimensiones, kNN de cinco vecinos y sin PCA**. Sobre 18 planos reservados obtuvo 16 aciertos, macro-F1 0,8261 y Precision@5 0,8889. Es evidencia exploratoria sobre cuatro categorías editoriales; no acredita rendimiento industrial ni equivalencia de precios.

La implementación y las pruebas se delegaron principalmente en cuatro agentes GPT-6.1 Sol. GPT-6 Astra realizó la revisión independiente. La petición posterior añadió organización documental, commit/push y pruebas de los otros datasets descargados. Estas pruebas adicionales se documentan por separado para no reinterpretar el test inicial como si hubiera evaluado todas las fuentes.

## Resultados de la ampliación a otros datasets

| Prueba | Entradas | Resultado observado | Qué significa |
|---|---:|---|---|
| Gemma 2 fijo en otras categorías CADBlock | 373 DXF admitidos de 379; test 55 | Macro-F1 0,7780; balanced accuracy 0,7719; P@5 0,7745 | Transferencia a 16 categorías editoriales adicionales de la misma fuente; el kNN aprende sus etiquetas con el nuevo train. |
| Identidad entre vistas PlankAssembly | 10 objetos, 30 vistas | Hit@1 y Hit@2: 0,300 | La correspondencia de un mismo objeto entre vistas es débil; no es una métrica de familia semántica. |
| Clasificador inicial frente a ingeniería | 14 DXF mecánicos | 11 buffets, 2 sofas, 1 simple-tables | El clasificador cerrado fuerza etiquetas de muebles; carece de rechazo fuera de dominio. |
| App offline en instantánea v2 | 53 archivos | Ingesta admitida; 53 runs generales pendientes de revisión, sin piezas ni propuestas | Abrir un archivo no implica obtener un despiece útil. El modo live no se ejecutó por configuración incompleta. |
| Importación de histórico público en app v2 | 4 registros | Cuatro aceptados y listados | Comprueba compatibilidad y persistencia de presupuestos académicos; no exactitud de costes. |

Los seis CAD rechazados por el laboratorio se desglosan en tres por geometría Z no nula y tres por un defecto de lectura de vértices SOLID/3DFACE. El lector del producto pudo abrirlos. No se ocultaron esas exclusiones ni se reinterpretaron como archivos inválidos.

La comparación posterior con Jev y clasificadores supervisados locales responde a otra petición del usuario. Reutiliza particiones cuyos resultados ya se habían visto; se documenta como comparación retrospectiva, no como un nuevo test ciego.

| Método, clasificación cerrada | Core test, 18 casos: macro-F1 | CAD adicional test, 55 casos: macro-F1 |
|---|---:|---:|
| EmbeddingGemma 2 mixto + kNN5 | 0,8261 | 0,7780 |
| Clasificador local seleccionado por validation | 0,8261 (kNN) | **0,8445** (logística EG2 + geometría, C=0,1) |
| Jev 1.14, render + texto geométrico | **0,9143** | 0,5249 |

Jev se ejecutó realmente mediante API: 320 respuestas válidas, con el modelo fijado y dos modalidades por caso. Su pregunta abierta rechazó 13/14 planos mecánicos con imagen. Estas observaciones no calibran un umbral operativo ni convierten la selección retrospectiva en evidencia ciega. Jev clasifica y ayuda a revisar; no genera el índice vectorial de recuperación que sí aporta EG2. La mejora del clasificador local tampoco cambia por sí sola los vecinos del embedding.

## Orden de lectura

| Documento | Qué contiene |
|---|---|
| [Auditoría y datos](AUDITORIA_Y_DATOS.md) | Qué hacía la aplicación en la base auditada; límites del harness, biblioteca y precios; fuentes locales y sus condiciones. |
| [Investigación de técnicas y modelos](INVESTIGACION_SOTA.md) | Fuentes primarias, EmbeddingGemma original frente a EmbeddingGemma 2, alternativas visuales/CAD y técnicas de reducción/agrupación. |
| [Metodología e implementación](METODOLOGIA.md) | Fronteras de entrada, representaciones, modelos, métricas, selección, congelación y comparador constructivo. |
| [Resultados iniciales](../SEMANTIC_LAB_2026-11-14.md) | Comparación de 228 configuraciones, test único, errores, revisión y evidencia numérica. |
| [Reproducción y artefactos](REPRODUCCION.md) | Entorno, comandos, archivos generados, caché, consultas y restricciones de reproducción. |
| [Revisión y decisiones](REVISION_Y_DECISIONES.md) | Hallazgos corregidos, lo que no se implementó, criterios para avanzar hacia muebles propios y costes. |
| [Aplicación con otros datasets](PRUEBA_APP_OTROS_DATASETS.md) | Pruebas de la aplicación real en una instantánea identificada; ingesta, extracción, abstención e histórico. |
| [Embeddings con otros datasets](PRUEBA_EMBEDDINGS_OTROS_DATASETS.md) | Transferencia del método congelado a entradas adicionales, resultados medidos y fallos fuera de dominio. |
| [Comparación con Jev](COMPARACION_JEV.md) | Clasificación por API de TypeSafe, contrato de decisión, modalidades, abstención y comparación retrospectiva. |
| [Clasificadores locales](COMPARACION_CLASIFICADORES_LOCALES.md) | Clasificación supervisada sobre embeddings/geometría, selección por validation y contraste con kNN. |
| [Cierre y verificación](CIERRE_Y_VERIFICACION.md) | Suite final, revisión Astra, contenido de publicación y límites del entregable. |

La [especificación](../superpowers/specs/2026-11-14-semantic-lab.md) y el [plan inicial](../superpowers/plans/2026-11-14-semantic-lab.md) conservan el alcance acordado. Los registros de agentes son evidencia de coordinación, no sustitutos del informe de resultados: [coordinación](../../team/agente_semantica_coordinacion.md), [datos](../../team/agente_semantica_datos.md), [modelos](../../team/agente_semantica_modelos.md), [evaluación](../../team/agente_semantica_evaluacion.md), [componentes](../../team/agente_semantica_componentes.md).

## Mapa del código

| Archivo | Responsabilidad |
|---|---|
| [features.py](../../tools/semantic_lab/features.py) | Lectura geométrica experimental, normalización, render y texto neutral. |
| [dataset.py](../../tools/semantic_lab/dataset.py) | Selección de corpus, grupos y particiones; manifiesto reproducible. |
| [encode.py](../../tools/semantic_lab/encode.py) | Inferencia local real, caché y procedencia de los ocho espacios probados. |
| [evaluate.py](../../tools/semantic_lab/evaluate.py) | Ajuste sólo con train, selección con validation y apertura explícita de test. |
| [query.py](../../tools/semantic_lab/query.py) | Consulta por ID en un índice existente; vecinos y predicción. |
| [components.py](../../tools/semantic_lab/components.py) | Comparación explicable de componentes V2/V3; controles sintéticos. |
| [probe_datasets.py](../../tools/semantic_lab/probe_datasets.py) | Protocolo fijo para CAD adicional, correspondencia de vistas y control mecánico fuera de dominio. |
| [probe_app.py](../../tools/semantic_lab/probe_app.py) | Prueba de API real en una instantánea aislada de aplicación, con persistencia local. |
| [classifier_comparison.py](../../tools/semantic_lab/classifier_comparison.py) | Comparación retrospectiva de kNN, logística y boosting sobre EG2/geometría. |
| [jev_comparison.py](../../tools/semantic_lab/jev_comparison.py) | Evaluación real Jev texto/imagen con preguntas cerradas/abiertas, caché y límites de solicitudes. |

Las pruebas correspondientes están en `tests/test_semantic_lab_*.py`. Este laboratorio no cambia los contratos ni añade un endpoint productivo de búsqueda con Gemma. La app y el laboratorio siguen siendo recorridos distintos.

## Evidencia que se publica

Los JSON pequeños de [experiments/semantic-lab-2026-11-14](../experiments/semantic-lab-2026-11-14/) contienen las 228 configuraciones, el config seleccionado, el test original, el resumen con procedencia, versiones y controles sintéticos. Los informes Markdown explican su lectura.

La [evidencia de otros datasets](../experiments/cross-dataset-2026-11-14/) conserva métricas, matrices, exclusiones y procedencia de la ampliación sin incluir originales de terceros.

La [evidencia de clasificadores](../experiments/classifier-comparison-2026-11-14/) conserva los resúmenes locales y de Jev, matrices, hashes, cobertura y consumo declarado de API. Las credenciales y respuestas crudas permanecen fuera de Git.

Los CAD, PDF de terceros, renders derivados, pesos y entornos no se incluyen en Git. En la máquina de ejecución están bajo los datasets del directorio `1hack` y `D:/Vexplorer-semantic-lab`. Un clon de esta rama contiene código y evidencia resumida; para repetir inferencias necesita acceso autorizado a las entradas y a los modelos.

## Cómo interpretar «funciona»

- **Ingesta:** puede abrir y registrar el archivo; no prueba extracción correcta.
- **Geometría:** obtiene observaciones y medidas con procedencia; no prueba identidad física ni cantidad de piezas.
- **Despiece:** requiere hipótesis o decisiones revisadas y una referencia independiente para medir exactitud.
- **Embedding:** genera un vector válido; su utilidad exige además evaluar vecinos y clasificación.
- **Similitud semántica:** aquí se midió principalmente coincidencia de categorías editoriales, con inspección visual complementaria.
- **Similitud constructiva/económica:** necesita componentes, materiales, operaciones, cantidades y un histórico compatible. Los resultados iniciales no la demuestran.

«Segmentación» en esta investigación significa agrupación/clasificación de objetos o documentos. No se implementó segmentación de píxeles, detección de cada mueble dentro de una escena ni identificación automática de cada pieza física.
