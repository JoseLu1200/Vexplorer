# Reconstrucción paramétrica: aclarar y regenerar

El usuario autoriza continuar con la vía paramétrica tras descartar Idol como motor principal. Se conserva la rama aislada y el alcance del registro personal. Este incremento completa el ciclo de aclaración del prototipo; no cambia contratos compartidos ni publica la app.

## Decisión

Continuar el harness existente, con revisiones inmutables. Reemplazarlo por Idol pierde piezas y escala; editar directamente una BOM sin revalidar separaría el dibujo del montaje. La propuesta elegida conserva plano, diagnóstico geométrico, revisión visual y exportaciones.

## Comportamiento

- El usuario responde a preguntas pendientes, indica uso previsto y puede aportar anchura, profundidad o altura generales en mm.
- POST /api/v1/reconstruction/{job_id}/refine crea un trabajo hijo, conserva el padre y reutiliza exactamente su imagen y metadatos congelados. Ninguna referencia privada interviene.
- Las respuestas son declaraciones del usuario, no medidas observadas en el plano. Se conservan acumuladas; una respuesta posterior a la misma pregunta sustituye su valor efectivo, con historial en los padres.
- Sólo se responden preguntas del resultado padre. Texto vacío, duplicados, trabajos activos y fuentes modificadas se rechazan antes de llamar al modelo.
- Las cotas generales son opcionales, positivas y finitas, máximo 100000 mm. El servidor comprueba la envolvente propuesta con tolerancia diagnóstica de 0,5 mm; envía incumplimientos al modelo y no publica como válida una propuesta que sigue incumpliéndolas.
- Una cota declarada por el usuario permite trabajar en mm, pero las dimensiones restantes siguen siendo hipótesis. Sin cota ni escala original se mantiene relative.
- Hasta diez refinamientos por cadena; máximo 32 respuestas efectivas. El modelo puede seguir absteniéndose. Sin precios, certificados ni aprobación automática de fabricación.
- El visor permite contestar, consultar los datos aportados y regresar a la versión anterior. Al regenerar limpia las piezas/descargas del resultado anterior para no atribuirlas al nuevo.
- Jobs antiguos sin contexto congelado siguen consultables, pero no refinables; deben generarse desde la entrada de nuevo.

## Verificación

Pruebas de servicio con proveedor simulado para reparación de cotas, abstención y procedencia; API real con executor para inmutabilidad, encadenado, unidades y rechazos; navegador para formulario, cambio de versión y ausencia de resultados antiguos. Se conserva el benchmark Idol sin alterar resultados.
