# Evaluación de la demo sintética

Este caso propio sirve para desarrollo y demostración del mecanismo: lectura de tres vistas montadas, conservación de desconocidos, escenarios de montaje y revisión humana versionada. No es una evaluación ciega ni una muestra representativa de producción.

La entrada permitida está en `data/planos_demo/`. La respuesta revisada vive en `evaluation/reference/`, fuera de cualquier ruta de runtime. La salida se congela antes de que el evaluador abra la referencia. Las alternativas justificadas se evalúan por separado de la coincidencia exacta.

PlankAssembly no se adapta ni se publica en esta tarea. Su preparación futura queda acotada a un trabajo separado: resolver licencia/uso, congelar IDs y familias, excluir la envolvente, conservar asociaciones, admitir `normal` ausente, generar vistas 2D con escala/unidades auditadas, sanear fugas y validar con fixtures independientes antes de medir inferencia.

