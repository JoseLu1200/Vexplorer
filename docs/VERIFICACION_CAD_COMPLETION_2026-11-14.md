# Ejecución real de CAD 2D — 14 de noviembre de 2026

Se integró `origin/main` (`4504adb`, explorador semántico incluido) en `feat/cad-completion` mediante `1e9a27a`. No se reimplementó ese explorador ni se modificó el checkout de la sesión de interfaz.

## Recorrido ejecutado

Carga HTTP del DXF → extracción y render de vistas → propuesta GPT-6.1 Sol → crítica GPT-6 Astra → validación de dimensiones y cantidades → persistencia P1/R1 → descarga HTTP de SVG/DXF. Sin revisión humana obligatoria. Configuración local: 16.384 tokens de salida por modelo, máximo 5 llamadas de revisión, 2 reparaciones de validación y presupuesto total de 600 segundos en el último caso.

| Control propio | Resultado real | Despiece provisional |
|---|---|---|
| F01, mesa | Job terminado; validación algebraica válida | Tapa 1200×600×30 (1), patas 720×50×50 (4), faldones 980×100×≈22 (2) y 380×100×≈22 (2). Espesor estimado: 18–30 mm. |
| F02, cajonera | Job terminado; validación algebraica válida | 7 tipos de piezas con 21 dimensiones numéricas; 23 piezas de tablero y 3 pares de guías comerciales sin geometría definida. |
| F03, estantería | Job terminado; validación algebraica válida | Costados 1800×300×18 (2), cierres 764×300×18 (2), estantes 764×300×18 (4). |

Los resultados y sus identificadores están congelados en [evaluation/results/cad_completion_live_2026-11-14](../evaluation/results/cad_completion_live_2026-11-14). Cada outcome conserva el hash SHA-256 del informe HTTP original, las piezas y láminas estructuradas, el estado de validación y los metadatos de descargas. No contiene claves, referencias privadas suministradas al modelo ni razonamientos internos. Los informes HTTP originales y descargas están en `.runtime/cad-completion-http/F01-02`, `F02-03` y `F03-02` del worktree.

## Correcciones verificadas durante la ejecución

- La crítica conserva referencias de evidencia propias de campos y cantidades, aunque no se repitan en el componente.
- Los parámetros tienen instrucciones explícitas de métodos admitidos y un presupuesto de ejecución compatible con propuestas extensas.
- Las dimensiones deducidas siguen siendo utilizables en escenarios provisionales sin promoverlas a observaciones.
- El generador exige una ubicación separada y explícita para referencias de evaluación.
- El evaluador se adapta a `piece_id`/`component_id` y a la procedencia de copias de cotas. Los cambios de vocabulario posteriores a observar resultados se declaran diagnósticos; no son una evaluación ciega.

## Alcance de la evidencia

Son tres controles creados por desarrollo, no planos independientes de clientes ni una medición de precisión industrial. La coherencia algebraica no prueba por sí sola una solución única. Las guías de la cajonera siguen sin dimensiones y las uniones se describen hasta donde existe geometría propuesta; no se afirma disponer de mecanizado CNC completo. El estado global puede conservar incógnitas aunque las dimensiones del tablero estén resueltas. No se ha desplegado este incremento en producción.

## Evaluación inicial congelada

La validación algebraica no equivale a utilidad completa. El evaluador diagnóstico de P1/R1 da F01 PASS (12/12 dimensiones), F02 FAIL (16/21 dimensiones y 15/21 bases de autoridad) y F03 FAIL (9/9 dimensiones, pero estabilización pendiente). No se modificaron las referencias ni sus tolerancias para hacerlos pasar.

En F02, dos discrepancias son un intercambio de los ejes de la trasera y una responde a una alternativa de unión coherente (testero 802 mm con laterales de 18 mm). El problema real es presentar como deducidos espesores trasladados a piezas ocultas. En F03 falta materializar el anclaje o arriostramiento. Se reforzó la crítica y reparación automática para ambos problemas y se reanudó desde las propuestas guardadas, sin enviar referencias privadas a los modelos.

La revisión visual corrigió cotas/textos recortados en dos láminas F02 y una tabla de piezas colapsada por las decisiones. La regeneración visual usa las mismas láminas estructuradas congeladas; no es una nueva inferencia.
