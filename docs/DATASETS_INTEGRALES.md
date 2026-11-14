# Inventario y admisión de datasets integrales

Auditoría local del 2026-11-14. Este documento distingue datos aptos para evaluar el objetivo de mobiliario, controles auxiliares y material no admisible. No incorpora oráculos al runtime ni concede derechos de redistribución.

## Resultado ejecutivo

La única fuente local con vistas de mobiliario y referencia de componentes suficientemente estructurada es PlankAssembly. Su referencia es paramétrica, no una revisión de planos pobres recibidos por la empresa, y sus vistas 2D son generadas por el adaptador. Sirve para un diagnóstico controlado de paneles, no para afirmar rendimiento industrial.

Cadblock aporta familias visualmente diversas de mobiliario y pares DWG/DXF, pero carece de despiece/BOM emparejado. Se admite para robustez de ingesta y comportamiento conservador, nunca como oráculo BOM. El corpus `engineering_dataset` es mecánico: sirve para cotas, PDF y conjuntos auxiliares, no para generalizar a muebles.

El workspace ya contiene 19 registros `published`: cuatro presupuestos académicos con coste/horas y quince coeficientes de tiempo de producción. Permiten ejercitar recuperación y estimación con alcance publicado, pero no son ERP, órdenes ejecutadas propias, juicios de relevancia de técnicos ni sesiones pareadas observadas. Por ello no permiten afirmar ahorro empresarial.

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
| Histórico público documentado en `FUENTES_HISTORICO_PUBLICO.md` | 4 presupuestos de muebles y 15 coeficientes de tiempo publicados | Dos artículos académicos con procedencia y licencia registradas | Coste/horas de alcance publicado; no ERP propio | QA económica y escenarios condicionales, nunca ahorro empresarial medido |

## Ampliación preparada

Se generaron `../plankassembly_adapter_test_v1` y `../plankassembly_adapter_test_v1_private` con el preparador existente, usando los diez primeros modelos del split oficial `test`. La operación no ejecutó inferencia y mantuvo programas/bounds/asociaciones solo en el directorio privado.

- 10 entradas DXF montadas, 10 ZIP individuales y hashes reproducibles.
- 10 referencias privadas; cero hashes de fuente solapados con los seis casos `valid` anteriores.
- 10 `family_hash` distintos; 9 quedaron marcados `development` y 1 `holdout` por la regla determinista del adaptador.
- 4–15 piezas físicas por caso, media 9,6. Cohortes estructurales: 1 caso de 3–5 piezas, 4 de 6–9 y 5 de 10 o más.
- Se verificaron todos los hashes de ambos directorios: 0 discrepancias.
- El manifiesto conserva `inference_evaluated: false` y `redistribution_authorized: false`.

Estas cohortes son de complejidad estructural, no tres familias semánticas de producto. PlankAssembly no publica etiquetas fiables de armario/mesa/estantería por modelo; inventarlas contaminaría la evaluación. Las diez entradas se congelaron y puntuaron después sin realimentar sus referencias al agente.

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

## Siguientes evaluaciones y límites

1. Las diez entradas públicas `test` y la cohorte pareada blind20 ya se congelaron y puntuaron sin ajustar prompt o matching tras abrir referencias.
2. Seguir informando por certeza factual, estado de revisión, cantidad, abstención y cobertura; la alineación por dimensiones no certifica identidad semántica.
3. Ejecutar los tres Cadblock solo como robustez de entrada/abstención. Sin oráculo, no calcular precision/recall BOM.
4. La operación automática no queda condicionada a revisión humana; debe conservar abstenciones, trazas y estados provisionales. Para medir ahorro empresarial sí hacen falta planos propios representativos, despieces o criterios de aceptación independientes, ERP compatible y sesiones pareadas observadas.

## Resultado live de los diez casos `test`

Tras congelar las diez respuestas live y su manifiesto SHA-256, se aplicó sin cambios el criterio previo: agrupación privada por tripleta dimensional, alineación uno-a-uno hasta 1 mm y ninguna realimentación al agente. Los diez proyectos y diez `family_hash` permanecen separados; el agregado no contiene bounds, programas ni descripciones privadas.

Resultado global: 88 tipos propuestos frente a 77 tipos dimensionales agrupados; 77 alineados (precisión 0,875, recobrado 1,000, F1 0,933). Once hipótesis de componente quedaron sin alineación. Se compararon 231/231 campos dimensionales, todos con estado `hypothesis`: MAE 0,719 mm y 229/231 dentro de 1 mm. La selección y agrupación pueden elevar esta coincidencia respecto a identidad semántica u ocurrencias exactas; no es una BOM certificada.

Las cantidades siguieron completamente desconocidas: cobertura 0/77 tipos y recobrado 0/96 ocurrencias. Ninguno de los diez escenarios locales se alineó con una construcción privada aceptable (0/10); se registran como no respaldados, no como falsos demostrados. Coste, horas, retrieval histórico, tiempos y correcciones carecen de denominador.

Por split, los nueve casos `development` obtuvieron tipos P=0,877/R=1,000/F1=0,934, 213/213 campos comparados, MAE 0,779 mm y 211/213 dentro de tolerancia; cantidades 0/89 ocurrencias. El único `holdout` obtuvo tipos P=0,857/R=1,000/F1=0,923, 18/18 campos dentro de tolerancia y cantidades 0/7. Un solo holdout no permite estimar generalización ni intervalos de rendimiento.

Informes agregados locales: `.runtime/transcript-qa/plank-test10-evaluation/report.json`, `report-development.json` y `report-holdout.json`. Las entradas privadas del evaluador permanecen fuera del producto y de Git.

## Cohorte pareada para revisor automático

Se preparó y ejecutó una cohorte posterior en `../plankassembly_adapter_blind20_v2` con referencia hermana privada. Usa el rango consecutivo 11–30 del split oficial `test`, por lo que no reutiliza los primeros diez casos ni los seis `valid`. Contiene 20 `family_hash` públicos distintos, 15 casos marcados development y 5 holdout. La dificultad visible oscila entre 36 y 192 entidades LINE por DXF (media 91,2) en las tres capas ortográficas.

Los ZIP que recibirá el harness contienen solo DXF y metadatos públicos acotados: ID opaco, formato, unidad, tipo de vista, instrucción y hash. Se eliminaron split y `family_hash` del ZIP individual; los 20 DXF carecen de TEXT/MTEXT, BOM, cantidades, IDs de pieza y rutas privadas. Los hashes públicos pasan y el directorio privado v2 no se abrió durante esta admisión. `blind20_v1` queda superado y no debe ejecutarse.

El ensayo conservó el primer borrador y la salida del crítico de una misma ejecución, con idéntico input/modelo/configuración; no comparó dos reruns estocásticos. Los 20 baselines y 19 finales, más un fallo de proveedor, se congelaron antes de abrir referencias. El manifiesto final contiene 192 archivos sin discrepancias. `auto_reviewed` es estado de revisión, no verdad ni confirmación humana; el hash enlaza artefactos, pero la cronología sigue siendo una afirmación de proceso auditada por el manifiesto/log.

Baseline: 115 tipos propuestos y 115 tipos dimensionales de referencia; 109 alineados (P=R=F1=0,948). Se compararon 327/345 campos (cobertura 0,948), 317 dentro de 1 mm, con MAE 6,331 mm. Cantidades provisionales: cobertura 104/115=0,904, 134/152 ocurrencias recuperadas, P=0,964/R=0,882/F1=0,921.

Final automático: 109 tipos propuestos, 99 alineados (P=0,908/R=0,861/F1=0,884); los tipos no alineados pasan de 6 baseline a 10 finales. Se compararon 297/345 campos auto-revisados (cobertura 0,861), 287 dentro de 1 mm, con MAE 6,970 mm. Cantidades auto-revisadas: cobertura 98/115=0,852, 127/152 ocurrencias recuperadas, P=0,977/R=0,836/F1=0,901. El crítico subió ligeramente la precisión de ocurrencias a costa de cobertura y recobrado. Los manifests contienen 109 cantidades y 342 dimensiones numéricas baseline frente a 101 y 309 finales: el fallo explica seis cantidades y 17 dimensiones perdidas; el enmascarado de decisiones no aceptadas explica las dos cantidades y 16 dimensiones restantes. Frente al baseline, 16 casos conservaron el número de tipos alineados y 4 lo redujeron; ninguno lo aumentó. Parte de esa caída es una propiedad del protocolo: un campo dimensional abstendido pasa a `null/unknown` y ya no puede participar en la alineación geométrica, por lo que el componente queda no alineado aunque su existencia no haya sido rechazada. El fallo del proveedor cuenta con salida final vacía, no se elimina del denominador. Los 19 outcomes finales quedaron `incomplete`, con `semantic_repairs=0`; esta cohorte no aporta evidencia de mejora por reparación de la propuesta/DXF, solo de revisión y abstención.

| Split / etapa | Tipos P/R/F1 | Dimensiones | Cantidad |
|---|---|---|---|
| Development baseline (15) | 0,950 / 0,927 / 0,938 | 228/246; 226 a 1 mm; MAE 0,158 mm | cobertura 72/82=0,878; F1 0,921 |
| Development final (15) | 0,905 / 0,817 / 0,859 | 201/246; 199 a 1 mm; MAE 0,179 mm | cobertura 67/82=0,817; F1 0,899 |
| Holdout baseline (5) | 0,943 / 1,000 / 0,971 | 99/99; 91 a 1 mm; MAE 20,547 mm | cobertura 32/33=0,970; F1 0,921 |
| Holdout final (5) | 0,914 / 0,970 / 0,941 | 96/99; 88 a 1 mm; MAE 21,189 mm | cobertura 31/33=0,939; F1 0,907 |

Los 20 escenarios baseline y 19 finales permanecen sin alineación semántica privada, por lo que se reportan como no respaldados y no como falsos demostrados. Para admitir un match se compara la tripleta dimensional sin orientación, como en test10; el error final sí conserva los campos largo/ancho/espesor. Por eso una asignación de ejes intercambiada puede contar como tipo alineado y a la vez elevar el MAE. Agrupar ocurrencias iguales y elegir una asignación óptima dentro de 1 mm puede inflar tipos frente a identidad semántica exacta; las abstenciones pueden reducirlos. Ni el subconjunto holdout de la misma fuente ni estos dibujos generados prueban generalización industrial. Costes, horas, retrieval y tiempos no forman parte de esta cohorte y conservan denominador cero; los 19 registros económicos publicados se evalúan por un protocolo separado y no convierten este resultado en ahorro medido.

Informes agregados locales: `.runtime/transcript-qa/blind20-evaluation/report-baseline.json`, `report-final.json` y sus particiones development/holdout. La alineación se reproduce con el CLI versionado `tools.build_panel_evaluation_references`; sus salidas se compararon objeto a objeto con las alineaciones que produjeron estas cifras. Las referencias y alineaciones privadas permanecen fuera del producto y de Git.
