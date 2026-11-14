# Evaluación semántica ampliada — 2026-11-14

Resultado: mejora modesta en concordancia de roles y ocurrencias; el problema funcional no queda resuelto. El montaje no está validado y la auditoría identifica límites ontológicos y de exhaustividad del benchmark. El swarm implementó correcciones y midió ambos snapshots sobre 30 planos reservados de un corpus propio de 80.

## Alcance

Trabajo ejecutado por swarm GPT-6.1 Sol: inferencia, montaje, dataset, evaluación y auditoría independiente, coordinados desde el repositorio. Se preservaron los cambios locales anteriores y se copió el código previo a `.runtime/semantic-v2-original` antes de las correcciones.

El problema era semántico: completar el recorrido técnico no acreditaba identificar las piezas, sus ocurrencias o relaciones. El crítico previo no podía solicitar piezas omitidas ni corregir funciones o grafo mediante una vía específica. Las instrucciones mezclaban apoyo funcional (`supported_by`) y fijación (`fixed_to`), y la evidencia visual solo anotaba un recorte bajo el presupuesto disponible.

## Correcciones

- Vocabulario canónico para funciones conocidas, manteniendo funciones nuevas explícitas en snake_case y desconocidos honestos.
- Revisión de inventario, roles y montaje con directivas cerradas y una reparación acotada; el servidor valida el delta y conserva campos no cuestionados.
- Alta de componente y relación correspondiente en la misma reparación, sin convertir hipótesis en hechos confirmados.
- Separación entre apoyo funcional y método de fijación; ninguna unión se deduce automáticamente solo del nombre del rol.
- Referencias visuales de contorno en las vistas generales.
- Métricas de recuperación completa: desconocidos cuentan como no recuperados; calidad condicionada, cobertura y aciertos opcionales se publican por separado.

## Corpus y comparación

Corpus sintético propio v2: 80 planos, 16 diseños/topologías, cinco perfiles de vista, al menos seis familias de mobiliario. Desarrollo/regresión: 50 planos de 10 diseños. Reservado: 30 planos de seis topologías v2 nuevas. Los diseños reservados de v1 pasan a desarrollo/regresión.

La separación usa proyecto, firma semántica estructural y una comprobación de firma visible normalizada; no acredita por sí sola independencia geométrica de toda posible proyección. Las variantes de un mismo diseño están correlacionadas. Los 30 planos reservados no equivalen a 30 diseños independientes.

Entradas públicas opacas y referencias privadas separadas. Las predicciones se congelan antes de abrir la referencia para puntuar. Original y corregido usan los mismos 30 IDs, Sol como proponente y crítico, tres trabajadores y límites idénticos. El hash del lote enlaza escenario, entrada y partición. Se informa por separado la propuesta inicial y la salida revisada.

No se comparan directamente estos F1 de recuperación completa con los F1 históricos condicionados a cobertura. Las uniones ocultas siguen registradas en la verdad de diseño, pero no son exigidas como observables a partir de vistas pobres.

## Resultados

Ambos snapshots completaron los 30 casos; las cuatro fases puntuadas tienen 0/30 casos completos contra la referencia. La mejora observada es modesta y no resuelve la validación funcional. Los F1 siguientes son concordancia léxica estricta con una referencia cerrada, no una estimación limpia de comprensión funcional: la auditoría posterior detectó desalineación de vocabulario y un grafo de referencia no exhaustivo.

| Versión / fase | Roles TP/FP/FN | F1 roles | Ocurrencias TP/FP/FN | F1 ocurrencias | Relaciones TP/FP/FN | F1 relaciones |
|---|---:|---:|---:|---:|---:|---:|
| Anterior / propuesta | 33/80/147 | 0,2253 | 46/111/234 | 0,2105 | 0/0/50 | 0 |
| Anterior / revisada | 32/81/148 | 0,2184 | 42/104/238 | 0,1972 | 0/0/50 | 0 |
| Corregida / propuesta | 37/74/143 | 0,2543 | 64/113/216 | 0,2801 | 0/90/50 | 0 |
| Corregida / revisada | 37/74/143 | 0,2543 | 55/100/225 | 0,2529 | 0/90/50 | 0 |

Tras revisión, el cambio es +0,0359 F1 en roles y +0,0557 en ocurrencias. La revisión de la versión corregida no mejora roles ni relaciones y reduce ocurrencias de 0,2801 a 0,2529. La nueva vía de reparación funciona en tests, pero no se activó en este lote: 0/30 reparaciones frente a 25/30 de la versión anterior. Ambas terminaron `incomplete` en 30/30; ninguna aprobó fabricación.

Los 90 FP de relaciones son tripletas no admitidas por esta referencia, no 90 uniones físicamente demostradas incorrectas. Se emitieron 44 `supported_by`, 44 `adjacent_to` y 2 `contained_by`; ningún triple completo coincidió en ambos extremos léxicos. La referencia anterior rev3 mantiene los mismos F1 de roles/ocurrencias y montaje 0, pero omite apoyos obligatorios en alternativas: FN de relaciones 35→50 para anterior y 20→50 para corregida. Se conserva esa sensibilidad, sin elegir el resultado favorable.

Los lotes rev2 con vistas superpuestas quedan excluidos del resultado principal y se conservan como diagnóstico. Ver [resumen detallado](../.runtime/semantic-v2-results/summary.md), [procedencia y hashes](../.runtime/semantic-v2-results/derivation-manifest.json) y [integridad de los freezes](../.runtime/semantic-v2-freeze-verification.json).

## Verificación

Baseline: 701 pruebas Python aprobadas. Tras corregir tres mocks de reparación que cambiaban campos sin solicitarlo, la suite completa final pasó: 793 pruebas, cero fallos, en 128,36 s. Las 14 pruebas de integración API también pasan. Ruff y git diff --check pasan sobre el alcance modificado. El repositorio contiene otro desarrollo concurrente de montaje 3D; el recuento global incluye sus pruebas disponibles, sin atribuirlas a este incremento.

## Límite práctico

Los diseños tienen verdad sintética conocida; no constituyen validación sobre planos industriales ni revisión técnica humana. Una hipótesis coherente no autoriza fabricación automática, tolerancias, mecanizados o herrajes. El informe debe conservar las carencias que revele la medición.

## Composición auditada del corpus

La generación contiene 7 casos easy, 35 medium y 38 hard. Sus 16 diseños suman 134 ocurrencias físicas únicas (entre 3 y 13 por diseño; media 8,38, mediana 9), repetidas en 670 exposiciones de vista. La verdad de diseño contiene 66 relaciones: 20 apoyos observables obligatorios y 46 uniones ocultas opcionales.

Además de la separación por firma semántica, una prueba compara firmas visibles normalizadas entre desarrollo y reservado. Esto mejora la higiene del split, sin demostrar generalización a todos los planos posibles. El sellado usa una única implementación canónica; la CLI del preparador delega en ella.


## Defecto del generador encontrado en inspección visual

Antes de puntuar, la inspección del caso público de desarrollo sx-001 mostró superposición entre planta y lateral. El desplazamiento heredado de v1 usaba el fondo donde debía reservar el ancho de la planta. Se corrigió solo la generación v2: cada proyección se normaliza y las cajas de vistas distintas quedan separadas al menos 100 mm. Una prueba recorre los 80 bundles y otra fija coordenadas esperadas independientes para un diseño 800 × 320. La generación histórica v1 permanece byte-compatible.

La revisión 3 conserva diseños, splits y referencias semánticas, y actualiza los hashes de entrada. Se repite la comparación completa con los mismos snapshots de runtime. No se ajustó el modelo a respuestas del reservado. SHA-256 del archivo público SHA256SUMS de rev3: `4a10f9d7f0164fea2d90f8d4e4df7dd612fac6e8723fd3f6542f6c4e35ff4c6b`. Las pruebas focales del corpus pasan 15/15; corpus/evaluador/runner pasan 49/49.


## Fe de erratas de anotación y análisis de sensibilidad

Una revisión del código del generador, antes de abrir las referencias para scoring, detectó que las alternativas reemplazaban todas las relaciones de un par por fixed_to, eliminando supported_by. El apoyo funcional y la fijación pueden coexistir. Se preserva la referencia rev3 y se prepara una referencia corregida rev4 que mantiene los apoyos requeridos. Las entradas públicas permanecen byte a byte iguales y no se altera el runtime.

Esta corrección de anotación es posterior al inicio de la inferencia y anterior al scoring; no se presenta como referencia original prefijada. Se evaluarán ambas versiones de referencia para publicar la sensibilidad, sin seleccionar el resultado más favorable. Ninguna respuesta privada ni puntuación motivó la corrección.


## Reproducibilidad de generación

Se detectó que ezdxf ordenaba los registros CLASS según PYTHONHASHSEED. La generación v2 actual canonicaliza ese orden y un test en procesos separados compara semillas 1 y 4 byte a byte. La generación histórica v1 conserva su serialización y requiere PYTHONHASHSEED=0 para comparación exacta. Este arreglo afecta solo futuras generaciones; los bundles rev3 usados en inferencia y su copia pública en el erratum permanecen intactos. Tras estos ajustes pasan 17 pruebas del corpus; después del arreglo del adaptador, la verificación conjunta corpus/evaluador/runner pasó 52 pruebas en 25 s.

## Interpretación de las métricas

Roles y ocurrencias evalúan etiquetas funcionales y cantidades agregadas por rol. El montaje principal evalúa relaciones requeridas entre roles; no certifica el encaje 3D de cada ocurrencia ni una unión de fabricación. Los métodos de fijación no observables se conservan aparte como opcionales. Un desconocido puede ser una abstención adecuada, pero sigue siendo información no recuperada en el F1 principal. Las predicciones correctas opcionales no elevan el recobrado de las relaciones obligatorias.


## Corrección del adaptador durante la puntuación

El primer intento de scoring rechazó las salidas corregidas porque varias relaciones entre ocurrencias distintas colapsaban a la misma tripleta al proyectar IDs a roles. El evaluador trabaja con un conjunto de tripletas por rol, por lo que el adaptador ahora elimina duplicados exactos después de esa proyección, también dentro de cada alternativa. No modifica cantidades físicas, predicados distintos ni direcciones. Una prueba independiente de dos patas del mismo rol reproduce el fallo y verifica la conversión.

Los nativos estaban congelados antes de abrir referencias. Los manifiestos semánticos derivados se regeneran después de esa apertura con la transformación pública corregida; se conservan los anteriores, sus rechazos y los hashes de procedencia. No se repite inferencia ni se cambian respuestas nativas, scoring o referencia. Esta cronología distingue la congelación nativa original del re-freeze del formato de evaluación.


## Carencias que permanecen

La auditoría independiente de desarrollo encontró 27 roles de referencia, 17 fuera del vocabulario preferido por el prompt. Hay equivalencias como desktop/tabletop, leg/table_leg o media_shelf/shelf que los aliases actuales no reconocen. Los aliases con guion son redundantes tras normalización. No se añadieron equivalencias a posteriori para mejorar el score.

El grafo de referencia es cerrado pero no exhaustivo. En el caso de desarrollo sx-001, el pipeline obtiene F1=1 en roles y ocurrencias y recupera el apoyo requerido, pero cinco relaciones adicionales plausibles cuentan como FP porque no están anotadas. Por eso el 0 TP exacto del reservado no demuestra ausencia de comprensión del apoyo funcional, y los 90 FP no cuantifican limpiamente errores físicos.

También persiste una descomposición insuficiente y una revisión que no recupera lo omitido. Este incremento corrige fallos de ejecución, representación, generación y medición; no convierte el sistema en un intérprete fiable ni en un aprobador autónomo. Para medir y cerrar esa carencia se necesita una ontología pública congelada con rol padre/subtipo, referencias de montaje revisadas como requerido/permitido/contradicho y una nueva evaluación independiente, además de planos reales anotados para estimar rendimiento de uso. Cambiar aliases o completar el gold después de ver este reservado no produciría una nueva prueba ciega.
