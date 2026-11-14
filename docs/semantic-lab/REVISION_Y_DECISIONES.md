# Revisión, decisiones y límites

## Alcance autorizado y versiones

El usuario pidió auditar el repositorio, investigar el estado del arte y probar diferentes métodos hasta obtener clasificación/recuperación semánticamente coherente. Solicitó explícitamente agentes GPT-6.1 Sol para implementación y GPT-6 Astra para revisión. Después pidió organizar todo en Markdown, ejecutar `git add`, `git commit`, `git push` y probar los otros datasets descargados.

El trabajo inicial se aisló en `.worktrees/semantic-lab`, rama `experiment/semantic-furniture`, base `4209510`. La aplicación evoluciona en paralelo en otra rama. Los hallazgos de la base auditada no se presentan como descripción eterna de esa rama paralela. Las pruebas adicionales de app identifican su propia instantánea y sus hashes.

No se modificaron contratos Pydantic ni runtime del producto para el experimento inicial. Los cambios de implementación iniciales son módulos nuevos bajo `tools/semantic_lab`, sus pruebas y extras de dependencias. Los datos y pesos permanecen externos. Publicar esta rama no implica merge, despliegue ni aprobación de nuevos contratos.

## Decisiones y motivos

| Decisión | Evidencia o motivo | Alcance |
|---|---|---|
| Usar CADBlock para el primer experimento | Planos 2D disponibles y diversidad visual inmediata. | Cuatro categorías proxy; no corpus técnico revisado. |
| Mantener juntas las vistas | Evitar contar vistas como objetos y fugas directas entre particiones. | Sigue existiendo riesgo de variantes visuales entre grupos. |
| Quitar textos, cotas y nombres de la entrada | Evitar que el modelo lea la categoría o identidad editorial. | No evalúa el beneficio real de anotaciones del harness. |
| Probar geometría además de redes | Baseline barata y explicable; macro-F1 0,914 en validation. | No conserva tamaño físico absoluto. |
| Probar Gemma visual y mixto | El texto geométrico por sí solo ofrecía poca semántica. | No equivale al descriptor completo de piezas. |
| Mantener 768d como ganador | Empató F1 con mixto256 y ganó en Precision@5 de validation. | No se compararon ambos en test para elegir después. |
| No usar PCA en el ganador | No mejoró el criterio de selección; PCA2 geométrico degradó F1. | No demuestra que PCA sea siempre inadecuado. |
| Conservar test tras dos errores | La selección ya estaba congelada. | Se documentó ruido de etiqueta sin relabelar para subir métricas. |
| Separar similitud visual y constructiva | Cambios de espesor/material pueden conservar forma visual. | Comparador de componentes sólo validado con controles sintéticos. |
| No estimar precios por coseno | No se dispone de validación económica asociada a los vecinos iniciales. | Hace falta otro dataset, criterio de relevancia y evaluación. |

## Hallazgos corregidos durante implementación

- Se eliminó una feature basada en proporción de entidades ignoradas: las anotaciones no deben introducir una señal involuntaria de categoría.
- Se corrigió la validación de campos requeridos en NPZ y se probaron IDs, finitud, filas y dimensión.
- Se normalizaron todos los vectores en float32 después de la inferencia BF16. Los NPZ anteriores no se usaron en la selección final.
- Se restringió Matryoshka a modelos/dimensiones declarados.
- En V3, los roles repetidos se suman en vez de sobrescribirse; reordenar o agrupar filas equivalentes no debe alterar el perfil.
- Las cantidades V2 desconocidas se explicitan como pesos de observación, nunca como unidades físicas demostradas.

## Revisión independiente inicial de Astra

Dictamen: **aprobado como experimento aislado, sin hallazgos bloqueantes pendientes para ese alcance**. No apto todavía para clasificación industrial, comparables de coste ni integración productiva.

| Hallazgo | Corrección y comprobación |
|---|---|
| El LP podía omitir parejas con afinidad cero | Objetivo en dos pasos: máxima masa compatible y luego afinidad. Test de materiales distintos sin dimensiones pasó de RED a GREEN. |
| El config congelado no estaba enlazado al informe | Nuevo hash canónico en selección y verificación de ganador/cluster al abrir test. Pruebas de config editado, informe ausente e incoherencia. |
| SciPy era sólo dependencia transitiva | Declaración directa en los extras del laboratorio, test y desarrollo. |
| Tabla DINOv3 no respetaba el desempate por retrieval | Precision@5 corregida a 0,859, coherente con el JSON de la mejor configuración. |

Astra contrastó el manifiesto y el embedding reales con sus SHA-256; comprobó inferencias con revisiones y `synthetic=false`, separación de grupos y ajuste train-only. El test histórico fue anterior al guard nuevo y se cotejó manualmente; no se fingió que el control nuevo hubiera protegido retroactivamente esa ejecución.

Verificación inicial final de coordinación: 466 tests aprobados en 60,66 s, Ruff sin hallazgos, compilación Python correcta, diff-check correcto y consulta CLI ejecutada. Las pruebas posteriores se documentan aparte; no se convierten en evidencia de nuevas inferencias si sólo verifican código.

## Qué sigue sin estar demostrado

1. **Generalización:** 117 planos de una fuente y 18 casos test son insuficientes. Tres clases test sólo aportan tres casos cada una.
2. **Taxonomía:** categorías editoriales incluyen mezclas; los errores de archivador/silla lo muestran.
3. **Independencia:** hashes y heurística nominal no equivalen a separación por fabricante, proyecto o diseño.
4. **Objetos desconocidos:** el clasificador cerrado fuerza una etiqueta conocida. No hay umbral de abstención calibrado.
5. **Despiece:** el embedding del documento no identifica por sí solo cada pieza, cantidad, unión o mecanizado.
6. **Agrupación libre:** KMeans se ajustó transductivamente y su k se eligió con etiquetas de validation.
7. **Construcción:** pesos manuales y controles sintéticos no validan intercambiabilidad real de componentes.
8. **Economía:** no se probó MAE de coste/horas ni que un vecino visual sea un comparable económico válido.
9. **Operación:** no hay endpoint nuevo para Gemma, índice vectorial distribuido, ingesta masiva segura ni monitorización de deriva.

## Siguiente evaluación válida

El corpus propio debería asociar planos y revisiones con familia revisada, medidas, materiales, acabados, piezas/cantidades, operaciones y campos desconocidos. Para evaluar precios necesita además coste real frente a presupuesto, moneda, fecha, impuestos, alcance, volumen y horas observadas. El índice debe conservar esas versiones y su fuente.

La partición debe hacerse por proyecto/fabricante y grupos de revisión antes de elegir modelos. Técnicos deben juzgar pares en dimensiones distintas: parecido visual, función, construcción y coste comparable. El modelo visual puede recuperar candidatos y la comparación estructurada reordenarlos; esa combinación se debe medir, no presumir.

Fijar criterios de aceptación antes del nuevo test: macro-F1/recall por familia, Precision/Recall/nDCG según juicios disponibles, cobertura y abstención, error económico por alcance compatible y tiempo de revisión observado. No inventar un umbral universal de coseno a partir de estas 18 consultas. No interpretar ahorro temporal como causal sin un estudio adecuado.

Las pruebas adicionales solicitadas sobre datasets locales son una comprobación de transferencia y compatibilidad. Sus resultados no sustituyen una evaluación industrial independiente.

## Qué añadió la comparación con Jev

La inspección del proyecto de tickets identificó un patrón útil: clasificación mediante preguntas tipadas, una salida abierta para `OTHER`/`UNKNOWN` y un juicio independiente de evidencia. Su adaptador histórico enviaba texto OCR. La API vigente se verificó por documentación y peticiones reales: Jev 1.14 también acepta imágenes. No se trasladaron métricas de tickets a mobiliario.

Sobre los casos actuales, Jev visual mejora la clasificación cerrada core de 16/18 a 17/18, pero rinde peor al ampliar a 16 categorías proxy. La logística sobre EG2 más geometría mejora el F1 de ese segundo corpus de 0,7780 a 0,8445. Son conclusiones descriptivas sobre tests previamente vistos y métodos con información distinta: Jev zero-shot conoce criterios de clase; los clasificadores locales aprenden con ejemplos etiquetados.

Esto apoya mantener tareas separadas: embeddings para recuperar candidatos, clasificación supervisada para una taxonomía conocida y una vía de abstención/revisión cuando la evidencia no encaja. No se implementó ni evaluó un ensemble que combine las salidas, un umbral de aprobación automática ni un estimador económico nuevo. El texto de seis magnitudes globales resulta pobre para Jev; este ensayo no evalúa un descriptor rico con roles, piezas y materiales revisados.
