# Inventario y admisión de datasets integrales

Auditoría local del 2026-11-14. Este documento distingue datos aptos para evaluar el objetivo de mobiliario, controles auxiliares y material no admisible. No incorpora oráculos al runtime ni concede derechos de redistribución.

## Resultado ejecutivo

La única fuente local con vistas de mobiliario y referencia de componentes suficientemente estructurada es PlankAssembly. Su referencia es paramétrica, no una revisión de planos pobres recibidos por la empresa, y sus vistas 2D son generadas por el adaptador. Sirve para un diagnóstico controlado de paneles, no para afirmar rendimiento industrial.

Cadblock aporta familias visualmente diversas de mobiliario y pares DWG/DXF, pero carece de despiece/BOM emparejado. Se admite para robustez de ingesta y comportamiento conservador, nunca como oráculo BOM. El corpus `engineering_dataset` es mecánico: sirve para cotas, PDF y conjuntos auxiliares, no para generalizar a muebles.

No hay en el workspace costes, horas, juicios de relevancia histórica ni tiempos observados de técnicos. Ningún dataset permite medir ahorro.

## Inventario

| Fuente local | Contenido observado | Procedencia/licencia registrada | Referencia disponible | Admisión |
|---|---|---|---|---|
| `../plankassembly_dataset` | 26.707 modelos oficiales; 24.039 train, 1.329 valid, 1.339 test; 3–19 piezas físicas por modelo | PlankAssembly, revisión local registrada; CC BY-NC-ND 4.0 | Bounds, normales cuando existen y asociaciones; primera fila es envolvente | Diagnóstico local de mobiliario de paneles. Sin redistribución ni uso comercial inferido |
| `../cadblock_2d` | 490 pares DWG/DXF planos y 7 pares con Z para revisión; 497 DXF con DIMENSION, 21 bibliotecas | cadblock.org; condiciones locales permiten uso en proyectos y prohíben revender/redistribuir la biblioteca | Sin BOM, detalle por pieza ni verdad de montaje | Ingesta, DWG→DXF, unidades y abstención; no precisión de despiece |
| `../cadblock_bulk` | Metadatos/evidencias históricas; los 997 STEP/GLB fueron enviados a la Papelera | Misma fuente/condiciones | No quedan binarios 3D locales | No usar como oráculo ni intentar restaurar/descargar sin necesidad nueva |
| `../engineering_dataset` | 50 conjuntos PDF Julius, Bench Vise, 14 piezas Orla DWG/DXF/PDF | Julius: personal/no comercial; Bench Vise: MIT declarado; Orla: CC BY-NC 4.0 | BOM completa solo de Bench Vise; cotas revisadas de una pieza; publisher records Orla | Control mecánico auxiliar, no mobiliario |
| `../engineering_evaluation_pilot_v3` | 17 casos: 14 extracciones CAD y 3 variantes PDF rasterizadas | Hereda fuentes anteriores | Referencia separada del evaluador | Desarrollo técnico, no 17 despieces ni test ciego |
| `../engineering_evaluation_pilot` y `_v2` | Preparaciones anteriores | Hereda fuentes anteriores | Versiones superadas; v2 no conserva correctamente todos los objetivos de abstención/desconocidos | No seleccionar para nuevos resultados |
| `../plankassembly_adapter_trial_v1{,_private}` | Seis casos del split oficial `valid` | Hereda CC BY-NC-ND 4.0 | Entrada pública y referencia físicamente separadas | Ya evaluado como diagnóstico de desarrollo v4; no benchmark ciego |

## Ampliación preparada

Se generaron `../plankassembly_adapter_test_v1` y `../plankassembly_adapter_test_v1_private` con el preparador existente, usando los diez primeros modelos del split oficial `test`. La operación no ejecutó inferencia y mantuvo programas/bounds/asociaciones solo en el directorio privado.

- 10 entradas DXF montadas, 10 ZIP individuales y hashes reproducibles.
- 10 referencias privadas; cero hashes de fuente solapados con los seis casos `valid` anteriores.
- 10 `family_hash` distintos; 9 quedaron marcados `development` y 1 `holdout` por la regla determinista del adaptador.
- 4–15 piezas físicas por caso, media 9,6. Cohortes estructurales: 1 caso de 3–5 piezas, 4 de 6–9 y 5 de 10 o más.
- Se verificaron todos los hashes de ambos directorios: 0 discrepancias.
- El manifiesto conserva `inference_evaluated: false` y `redistribution_authorized: false`.

Estas cohortes son de complejidad estructural, no tres familias semánticas de producto. PlankAssembly no publica etiquetas fiables de armario/mesa/estantería por modelo; inventarlas contaminaría la evaluación. Las diez entradas pueden congelarse con inferencia nativa antes de que el evaluador abra sus referencias, replicando el protocolo v4.

## Tres familias visuales para robustez, sin oráculo BOM

Cadblock sí ofrece familias nominales, pero solo como bloques arquitectónicos. Se admiten tres casos públicos adicionales para comprobar lectura conservadora, no exactitud de componentes:

| Familia | Entrada local | Smoke observado |
|---|---|---|
| Mesilla/cajonera | `../cadblock_2d/dxf_metric/beds/three-drawer-nightstand-round-knobs-rounded-corners-plan-metric.dxf` | `ready`, metros, 93 entidades, 3 contornos, 6 cotas |
| Archivador | `../cadblock_2d/dxf_metric/simple-tables/four-drawer-vertical-filing-cabinet-letter-size-front-elevation-metric.dxf` | `ready`, metros, 38 entidades, 10 contornos, 6 cotas |
| Mesa de centro | `../cadblock_2d/dxf_metric/sofas/rectangular-coffee-table-inset-top-plan-metric.dxf` | `ready`, metros, 69 entidades, 1 contorno, 6 cotas |

Los tres se abrieron con `extract_drawing` sin avisos. El extractor actual los agrupa en una vista, pese a que el catálogo anuncia planta/alzado/lateral; esto debe tratarse como limitación de segmentación, no como una BOM. Títulos, nombres de archivo y categorías son metadatos públicos de la fuente y no equivalen a componentes internos.

## Fuentes rechazadas para el objetivo principal

- Julius de Waal, Bench Vise y Orla son mecánicos. Pueden probar PDF, cotas y referencias, pero no semántica ni costes de mobiliario.
- Los bloques de camas, sofás y comedores de Cadblock mezclan muebles, cojines, ropa y sillas; sin detalle de fabricación no existe una respuesta BOM independiente.
- Los 985 JSON PlankAssembly no listados en splits oficiales quedan fuera de cualquier comparación.
- No se usarán nombres de fuente, programas JSON, sidecars, bounds privados o asociaciones como entrada al agente.
- No se descargará otro corpus solo para aumentar recuentos mientras no aporte emparejamiento, licencia utilizable y referencia revisable superior a PlankAssembly.

## Siguiente evaluación autorizable

1. Ejecutar y congelar las diez entradas públicas `test` con el mismo modelo/prompt/schema y guardar hashes antes de puntuarlas.
2. Puntuar agregados por separado de los seis casos `valid`; no ajustar prompt o matching tras ver referencias.
3. Informar por estado `hypothesis|observed|confirmed`, cantidad, abstención y cobertura; la alineación por dimensiones no certifica identidad semántica.
4. Ejecutar los tres Cadblock solo como robustez de entrada/abstención. Sin oráculo, no calcular precision/recall BOM.
5. Para cerrar la transcripción siguen siendo imprescindibles planos pobres reales de al menos tres familias empresariales, despieces revisados, histórico de comparables, costes/horas compatibles y sesiones de técnicos.

## Resultado live de los diez casos `test`

Tras congelar las diez respuestas live y su manifiesto SHA-256, se aplicó sin cambios el criterio previo: agrupación privada por tripleta dimensional, alineación uno-a-uno hasta 1 mm y ninguna realimentación al agente. Los diez proyectos y diez `family_hash` permanecen separados; el agregado no contiene bounds, programas ni descripciones privadas.

Resultado global: 88 tipos propuestos frente a 77 tipos dimensionales agrupados; 77 alineados (precisión 0,875, recobrado 1,000, F1 0,933). Once hipótesis de componente quedaron sin alineación. Se compararon 231/231 campos dimensionales, todos con estado `hypothesis`: MAE 0,719 mm y 229/231 dentro de 1 mm. La selección y agrupación pueden elevar esta coincidencia respecto a identidad semántica u ocurrencias exactas; no es una BOM certificada.

Las cantidades siguieron completamente desconocidas: cobertura 0/77 tipos y recobrado 0/96 ocurrencias. Ninguno de los diez escenarios locales se alineó con una construcción privada aceptable (0/10); se registran como no respaldados, no como falsos demostrados. Coste, horas, retrieval histórico, tiempos y correcciones carecen de denominador.

Por split, los nueve casos `development` obtuvieron tipos P=0,877/R=1,000/F1=0,934, 213/213 campos comparados, MAE 0,779 mm y 211/213 dentro de tolerancia; cantidades 0/89 ocurrencias. El único `holdout` obtuvo tipos P=0,857/R=1,000/F1=0,923, 18/18 campos dentro de tolerancia y cantidades 0/7. Un solo holdout no permite estimar generalización ni intervalos de rendimiento.

Informes agregados locales: `.runtime/transcript-qa/plank-test10-evaluation/report.json`, `report-development.json` y `report-holdout.json`. Las entradas privadas del evaluador permanecen fuera del producto y de Git.

## Cohorte ciega para revisor automático

Se preparó una cohorte posterior, todavía sin inferencia ni puntuación, en `../plankassembly_adapter_blind20_v2` con referencia hermana privada. Usa el rango consecutivo 11–30 del split oficial `test`, por lo que no reutiliza los primeros diez casos ni los seis `valid`. Contiene 20 `family_hash` públicos distintos, 15 casos marcados development y 5 holdout. La dificultad visible oscila entre 36 y 192 entidades LINE por DXF (media 91,2) en las tres capas ortográficas.

Los ZIP que recibirá el harness contienen solo DXF y metadatos públicos acotados: ID opaco, formato, unidad, tipo de vista, instrucción y hash. Se eliminaron split y `family_hash` del ZIP individual; los 20 DXF carecen de TEXT/MTEXT, BOM, cantidades, IDs de pieza y rutas privadas. Los hashes públicos pasan y el directorio privado v2 no se abrió durante esta admisión. `blind20_v1` queda superado y no debe ejecutarse.

El ensayo debe conservar el primer borrador y la salida del crítico de una misma ejecución, con idéntico input/modelo/configuración; no comparar dos reruns estocásticos. Ambos artefactos y sus SHA-256 se congelan antes de abrir referencias. La evaluación publicará reparaciones mejoradas/regresadas, abstenciones, componentes no respaldados, escenarios y cantidad/ocurrencias provisionales. `auto_reviewed` es estado de revisión, no verdad ni confirmación humana. El hash enlaza artefactos, pero la cronología sigue siendo una afirmación de proceso auditada por el manifiesto/log.
