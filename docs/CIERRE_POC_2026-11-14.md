# Cierre de abstención, evaluación semántica y versión

## Alcance

El usuario solicitó corregir abstenciones evitables, disponer de referencias de función/montaje/piezas omitidas/alternativas, preparar un corpus reservado (permitiendo síntesis), consolidar los cambios locales y cerrar la aceptación PDF raster. Ejecución mediante agentes GPT-6.1 Sol y revisión final GPT-6 Astra.

## Diagnóstico y cambios

- El gate de revisión mezclaba geometría con material/acabado ausentes. Ahora solo se puede normalizar esa incompletitud cuando los demás campos y comprobaciones están cubiertos; dudas de identidad o montaje siguen pendientes.
- Una abstención dimensional sobre un valor desconocido puede recibir una reinspección acotada si hay segmentos métricos en el ledger. No añade cifras ni fuerza aceptación; la nueva propuesta vuelve a validarse.
- Los checks aceptados deben apuntar al campo exacto. La cantidad requiere comprobaciones dirigidas de base de cantidad y ausencia de duplicados.
- El contrato aditivo permite relaciones y alternativas de montaje con premisas y referencias cerradas, siempre hipotéticas/desconocidas/conflictivas. Se conservan en propuesta, borrador, reparación y snapshots; no añaden ocurrencias.
- PDF raster anuncia explícitamente sus referencias permitidas y la ausencia de autoridad métrica. Los errores de proveedor conservan motivos operativos acotados, sin cuerpos remotos ni secretos.
- QA detectó y corrigió tres defectos adicionales: nota de biblioteca obsoleta, GET prematuros de derivados todavía inexistentes y formulario que exigía motivo de escala incluso cuando no se confirmaba ninguna.
- Empaquetador reproducible con allowlist, dependencias, manifiesto y hash de payload. Los cambios UX/auth anteriores se preservan y se consolidan con esta entrega.

## Corpus y método

18 casos sintéticos propios: 12 de desarrollo y 6 reservados, agrupados en seis proyectos/topologías. Las tres clases de producto aparecen en ambos splits; no es una evaluación de clases de mobiliario no vistas. Los cuboides tienen medidas positivas y no se interpenetran. Los casos reservados incluyen variantes relacionadas: seis planos no equivalen a seis diseños independientes.

Los ZIP públicos contienen solo DXF y metadatos mínimos compatibles con el runner estricto. Las referencias privadas se mantienen separadas; sus funciones, relaciones y alternativas no se entregan al runtime. El agente que generó los datos retiene las respuestas hasta la congelación de las predicciones. Los hashes acreditan integridad, no independencia industrial ni cronología criptográfica.

El evaluador distingue roles, ocurrencias y relaciones; registra cobertura y desconocidos. Los oráculos se identifican como `design_known_synthetic`, nunca como revisión de un técnico. La síntesis cierra la disponibilidad de un benchmark controlado, no sustituye una prueba con planos reales de la empresa.

## Verificación y resultados

Estado de este registro: integración y ensayos en curso. No constituye aceptación final todavía.

- Baseline inicial ejecutada por raíz: 606 pruebas Python y 162 JavaScript aprobadas.
- Revisión independiente de los artefactos históricos: 192 hashes de blind20 coinciden. Reaplicar el nuevo gate conserva los 19 casos incompletos por dudas estructurales, sin mejorar artificialmente sus etiquetas.
- Verificación propia del corpus público: 18 bundles aceptados por el lector estricto; siete pruebas de generación aprobadas.
- Verificación propia del empaquetador: tres pruebas aprobadas.
- Verificación propia de contrato/montaje: quince pruebas aprobadas.

Pendientes en este checkpoint: suite conjunta definitiva, inferencia de desarrollo y reservada, evaluación posterior al freeze, aceptación raster HTTP, QA final, revisión Astra, commit y hash definitivo del paquete.

## Documentos relacionados

[Corpus](CORPUS_SEMANTICO.md), [evaluación semántica](EVALUACION_SEMANTICA.md), [PDF raster](VERIFICACION_PDF_RASTER.md), [producción](PRODUCCION.md), [plan](superpowers/plans/2026-11-14-poc-closure.md).
