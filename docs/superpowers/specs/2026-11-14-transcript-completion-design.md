# Ampliación funcional de la transcripción

Solicitud: implementar los huecos descritos en `transcripcion-contexto-poc.md` mediante agentes GPT-6.1 Sol, con GPT-6 Astra como revisor. La solicitud renueva la autorización del swarm de IA existente; no se deducen identidades humanas. Base: `4209510`.

## Decisiones de implementación

Se amplía FastAPI/Pydantic y el frontend JS existente. Se conserva el recorrido de mesa y piezas separadas. La alternativa de extender solamente plantillas no satisface la propuesta de piezas generales; reemplazar el producto completo perdería revisión y evidencia existentes. Se añade un recorrido genérico de componentes de panel, con herramientas nativas, referencias geométricas, hipótesis explícitas y edición técnica versionada. Esta decisión no acredita reconocimiento universal ni aptitud industrial.

La entrada admite DXF, DWG mediante conversor instalado y PDF vectorial o rasterizado. El PDF conserva página, coordenadas fuente y preview; solo una escala explícitamente confirmada puede convertir medidas gráficas a mm. Un raster no genera geometría medida ficticia. Conversor ausente se comunica como tal.

El histórico económico se importa con fuente, fecha, moneda, naturaleza real/sintética y conceptos disponibles. Los factores de coste y horas se calculan con código sobre consumos comparables; se mantienen costes fijos y faltantes. La similitud no autoriza trasladar precios entre materiales incompatibles. Datos empresariales desconocidos no se sustituyen por ejemplos inventados.

La evaluación consume predicciones congeladas y referencias reservadas por separado. Calcula calidad de piezas/cantidades/dimensiones, relevancia de recuperación, errores de costes/horas, cobertura y tiempos pareados. Los fixtures de desarrollo no demuestran ahorro empresarial.

## Propiedad y coordinación

- Ingesta: adaptadores PDF/DWG y pruebas.
- Backend general: contratos aditivos (único escritor tras acuerdo A/B), propuestas, revisión, derivados, persistencia y router propios.
- Economía: importación, catálogo histórico, comparables, estimación y router propios.
- Evaluación: métricas y CLI fuera del runtime.
- Frontend: carga, revisión general, histórico y estimaciones accesibles.
- Integración: `backend/app/main.py`, montaje de routers y pruebas HTTP.
- Coordinación: documentación, verificación conjunta y entrega.
- Astra: revisión independiente de código y evidencia, sin implementación.

## Criterios

No alterar medidas observadas con cifras propuestas por un modelo. Cantidades físicas distintas de número de vistas. Incógnitas permanecen desconocidas. Edición requiere motivo/autor y conserva versiones. Autenticación y prefijo privado deben cubrir rutas nuevas. Imports y conversiones tienen límites de recursos. Las referencias reservadas no llegan al agente. Verificar recorridos nuevos y regresiones antes de declarar resultados.

## Revisión automática solicitada durante la implementación

El usuario elimina expresamente el requisito de revisión humana: solicita aprovechar la capacidad multimodal para revisar los planos, corregir las propuestas y mejorar el harness. El recorrido live general pasa a propuesta visual, crítica en un contexto separado, reparación acotada y derivados automáticos. La edición manual queda opcional; una incógnita se conserva como tal sin obligar a una persona a resolverla.

El proponente y el revisor reciben imágenes renderizadas de la fuente DXF/DWG o la página PDF, junto con referencias cerradas del ledger. Los recortes y las asociaciones entre proyecciones se basan en geometría pública. Los píxeles ayudan a interpretar; los valores métricos proceden de medidas deterministas referenciadas. La relación entre modelos se registra desde la configuración real del servidor: revisión con el mismo modelo o con otro modelo, sin afirmar independencia estadística.

La revisión es un eje separado del estado factual. Un valor inferido conserva `hypothesis` después de la revisión automática. Las cantidades inferidas pueden producir ocurrencias y planos provisionales de un escenario, identificados por separado de las ocurrencias confirmadas. Los controles deterministas, los límites, los conflictos y la trazabilidad se aplican a ambas salidas. Ninguna afirmación del revisor convierte una hipótesis en una observación.

La evaluación pareada congela la primera propuesta y el resultado del crítico sobre la misma entrada antes de consultar referencias. Los dieciséis casos ya utilizados quedan como diagnóstico; se prepara una cohorte nueva de veinte. Se miden aciertos, componentes extra, cantidad provisional, ocurrencias, escenarios, cobertura, abstenciones y regresiones de reparación. Este ensayo puede demostrar mejoras automatizadas; no crea por sí solo evidencia sobre ahorro de tiempo de una empresa.
