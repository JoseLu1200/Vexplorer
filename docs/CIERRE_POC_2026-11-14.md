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

Integración y ensayos funcionales completados. La aceptación técnica del software no implica aceptación semántica industrial: el conjunto reservado muestra un rendimiento insuficiente para validar montaje autónomamente.

- Baseline inicial ejecutada por raíz: 606 pruebas Python y 162 JavaScript aprobadas.
- Revisión independiente de los artefactos históricos: 192 hashes de blind20 coinciden. Reaplicar el nuevo gate conserva los 19 casos incompletos por dudas estructurales, sin mejorar artificialmente sus etiquetas.
- Checkpoint inicial del corpus público: 18 bundles aceptados por el lector estricto; siete pruebas de generación aprobadas.
- Checkpoint inicial del empaquetador: tres pruebas aprobadas.
- Checkpoint inicial combinado de contrato/montaje: quince pruebas aprobadas.

### Checkpoints de integración observados

- Tras integrar en la rama aislada: 653 pruebas Python aprobadas; tras las correcciones siguientes de referencias/procedencia: 662 aprobadas. Son checkpoints, no sustituyen la comprobación del árbol final.
- Frontend integrado: 164 pruebas aprobadas y QA de navegador de DXF, revisión, biblioteca, costes, derivados, exportaciones, vista móvil y PDF sin escala, con consola limpia.
- Aceptación HTTP raster real: job `succeeded`, seis componentes y 18 ejes `null/unknown`, sin vistas métricas inventadas. Informe SHA-256 `164cf7b5aa1e0080b9b60117c58493404533b845e238f0f7f1594ee369d1051c`. Se conserva el fingerprint del código cargado; el ensayo precede al refinamiento posterior del prompt semántico.
- Desarrollo v1: una ejecución completa en 101,374 s; roles libres no alineados y sin relaciones propuestas. Desarrollo v2, tras explicitar semántica: fallo antes de baseline por notación de referencias de montaje. Se conserva el fallo; las tres propuestas capturadas se reprodujeron offline y materializaron correctamente tras aceptar únicamente aliases exactos y unívocos del ledger.
- Reservado v1: tres ejecuciones completas (`sx-013`, `sx-014`, `sx-015`) y tres fallos previos al proveedor (`sx-016`, `sx-017`, `sx-018`) por exceder el número de recortes visuales opcionales. Manifiesto congelado SHA-256 `424a68b3a962d8ab98cd491f46c6f3a8cf7b999315cf237f730ef0b383c2e93b`.
- Antes de abrir el oráculo se fija esta política de recuperación: repetir únicamente esos tres fallos previos al proveedor, conservar byte a byte las tres salidas exitosas, mantener seis casos en el denominador y registrar manifiestos/configuración/código por origen. No seleccionar resultados según puntuación ni repetir inferencias exitosas.

### Aislamiento y trabajo concurrente

Durante el cierre comenzó otra sesión de similitud sobre el mismo checkout. El trabajo de esa sesión y todos los cambios previos se conservan en el árbol original. Esta entrega se verifica en `.worktrees/poc-closure`, rama `feat/poc-closure`, basada en `c94a888`, sin incorporar implementaciones parciales del otro swarm. Las tres correcciones QA propias se reaplicaron y probaron en la copia aislada.

### Revisión independiente

Astra detectó antes de la aceptación: recetas reservadas exactas presentes en fuente del generador, métrica de alternativas incompatible con las dos opciones del contrato runtime, cobertura agregada de alternativas ausente y comprobación raster que exigía valores nulos pero no el estado desconocido. Los cuatro hallazgos se corrigieron y Astra los volvió a verificar. Su dictamen aprueba la entrega de software sujeto al recibo de commit y doble empaquetado; no acepta la capacidad semántica autónoma. También exigió que la recuperación distinguiera el error exacto previo al proveedor de cualquier fallo anterior a baseline; la herramienta comprueba ahora tipo, mensaje y ausencia de evidencia de llamadas.

### Resultado definitivo del ensayo reservado

Los tres reintentos terminaron correctamente. Se mantienen seis casos en el denominador, las tres salidas originales exitosas byte a byte y los tres errores iniciales archivados. El lote combina dos fingerprints de código de forma explícita; no se presenta como una sola ejecución del árbol final.

| Métrica | Baseline | Tras revisión |
| --- | ---: | ---: |
| Roles, F1 | 0,4000 | 0,4000 |
| Ocurrencias físicas, F1 | 0,4706 | 0,4848 |
| Ocurrencias físicas, recall | 0,3902 | 0,3902 |
| Relaciones de montaje, recall | 0 | 0 |
| Alternativas constructivas, recall | 0 | 0 |

La revisión reduce dos falsos positivos de ocurrencia; no recupera más piezas ni mejora roles/montaje. La cobertura declarada no equivale a acierto. Roles y montaje siguen siendo hipótesis no revisadas por el crítico dimensional. El corpus comprende tres diseños reservados y dos variantes por diseño, no seis diseños independientes. No se ajustó el runtime tras abrir estos resultados.

Artefactos locales bajo `.runtime/poc-closure-benchmark`:

- Recuperación `heldout-recovery-v1/frozen-manifest.json`: `803b93348af057c31364b7e39fbca0f3e332ffa572176126c8b2936a110a3d1a`.
- Cohorte `heldout-merged-v1/frozen-manifest.json`: `782750b45432a16ccf84d7bf8de0608a984c949609b5b6307cfaa7e7a7d118b1`.
- Predicciones semánticas baseline: `489dc57bfa19ef8bcb3a10b589ad39d6c42e42ff1967b096e0a7e5c1bf2a1e01`.
- Predicciones semánticas finales: `bbf0d936b69def44a635599f496793ae8e523622140975440f6e87a9b4f0540c`.
- Informe baseline: `6c40da00687d5a79828a2aa15d6bb58d32af11ae658ea4b6baabf931ef82080c`.
- Informe final: `5d523ac35be670d50ff5155ea3edb97f1168fe81f93d36f207fd0a86635bc474`.

El sello se realizó después de congelar predicciones. Los timestamps del merge son metadatos fijos, no prueba criptográfica de cronología. Un locator de custodia externo permite al evaluador del usuario recuperar referencias y recetas sin introducirlas en Git ni en el release; no debe entregarse al runtime.

### Comprobación del árbol de entrega

- Suite completa: **683 pruebas Python aprobadas**, dos avisos de deprecación; **164 JavaScript aprobadas**.
- QA de navegador y autenticación completado en la rama aislada; véase el registro QA.
- `git diff --check` correcto. Ruff focal limpio; el barrido ampliado registra ocho avisos de imports/variables sin uso en líneas preexistentes de main y tests, por lo que no se declara lint global limpio.
- Dos empaquetados del mismo árbol producen bytes idénticos; payload SHA-256 `f57b11ebfdf16611ffc8e3ebac405a3210ca08e9f17342d78366c0f2793fe2ae`, 110 archivos. El recibo local `.runtime/release-final/receipt.json` identifica commit y archivo tras consolidar Git.
- No se ha desplegado este candidato al servidor. El estado remoto anterior queda documentado por separado.

### Límites que permanecen abiertos

Se cierra la infraestructura de abstención justificada, referencias sintéticas privadas, medición semántica, trazabilidad y recorrido raster. No se declara resuelta la exactitud semántica autónoma: faltan mejoras demostradas en piezas omitidas, roles y montaje, y validación con planos reales revisados por técnicos. Las abstenciones por evidencia realmente ausente deben mantenerse. La síntesis autorizada cubre el banco controlado solicitado, no acredita fabricabilidad.

## Documentos relacionados

[Corpus](CORPUS_SEMANTICO.md), [evaluación semántica](EVALUACION_SEMANTICA.md), [PDF raster](VERIFICACION_PDF_RASTER.md), [producción](PRODUCCION.md), [plan](superpowers/plans/2026-11-14-poc-closure.md).
