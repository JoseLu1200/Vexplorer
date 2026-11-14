# Reparación de Biblioteca y similitud

Solicitud: resolver los seis hallazgos del usuario, con implementación GPT-6.1 Sol y revisión GPT-6 Astra. Mantener la arquitectura determinista y los cambios locales previos.

## Decisiones

El coseno representa parecido de tipología, no identidad de fabricación. Recuperar candidatos semánticos y ordenarlos con comparación técnica explícita. Mantener separadas diferencias e incertidumbres de material/acabado, sin inferir equivalencia económica. Deduplicar diseños antes del límite; conservar referencias a sus registros. Comparar piezas canónicas y mostrar diferencias, incluidas dimensiones interiores. Agrupar con criterio por pares y explicarlo; un umbral permisivo puede legítimamente producir un grupo.

## Tareas y propiedad

1. Motor (`backend/app/similarity/service.py` y pruebas propias): reproducir cambios 18→36 y 864→828, añadir comparación técnica y diferencias canónicas, agrupación determinista sin cadenas engañosas. Acordar interfaces con API.
2. API (rutas Biblioteca/similitud de `backend/app/main.py`, helpers y pruebas propias): deduplicar antes de truncar, contar diseños/registros, separar coseno y score técnico, preservar versiones y errores. Contratos aditivos solo tras acuerdo motor/API y aviso UI.
3. UI (`frontend/app.js`, `index.html`, `styles.css` y pruebas propias): precisión sin falsa identidad, conteos y vacíos explicados, comparativas por pieza y miniaturas disponibles, material/acabado desconocidos visibles, criterio y control de umbral.
4. Operación (tooling/docs propios): diagnosticar Biblioteca publicada vacía y persistencia; preparar remedio con registros elegibles y procedencia; respaldar y verificar antes de cualquier publicación. No inventar muebles ni importar histórico económico como Biblioteca.
5. Evaluación (módulo y pruebas nuevos): familias distintas, variantes difíciles, materiales, desconocidos, duplicados y cadenas. Vectores de prueba claramente sintéticos; evidencia real separada.
6. Coordinación: ejecutar comprobaciones integradas, inspeccionar diff, revisión fresca Astra, resolver hallazgos, verificar publicación y documentar límites.

## Casos de aceptación

- Una similitud 0,999546 no se presenta como identidad; espesor doble e interiores diferentes son visibles.
- Reordenar piezas o cambiar IDs no crea alternativas ficticias; cinco registros no equivalen a cinco diseños.
- Material/acabado diferentes o ausentes no se presentan como compatibles por tener igual geometría.
- A–B y B–C sobre umbral no permiten afirmar A–C sobre umbral.
- Proveedor configurado y biblioteca vacía se distinguen; la persistencia se comprueba con datos reales existentes.
- Resultados sin embedding, versiones incompatibles y campos desconocidos conservan avisos y exclusiones verificables.

## Validación

Pruebas RED→GREEN en cada tarea; `python -m pytest -q`, `npm test --prefix frontend`, evaluación independiente, verificación de sintaxis y diff, revisión Astra sobre cambios reales y comprobación navegador. Registrar resultados observados, no estimaciones de éxito.
