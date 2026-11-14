# Plan de implementación: completar CAD 2D

Fuente: [encargo y diseño](../specs/2026-11-14-cad-completion.md).

- [x] Congelar un contrato compacto de construcción y dimensión observada/deducida/estimada, con ejemplo completo compartido entre agentes.
- [x] Resolver parámetros y operaciones; validar cierres, espesores, vanos y cantidades sin modificar observaciones.
- [x] Extender el harness nativo para interpretar el mueble, completar piezas y detalles, estimar faltantes y corregir contradicciones automáticamente.
- [x] Producir lista provisional con valores estimados explícitos y planos SVG/DXF acotados por pieza.
- [x] Conectar la interpretación, los planos y la explicación priorizada en la interfaz 2D y API persistente.
- [x] Crear tres controles propios de vistas montadas y referencias por escenarios, sin respuestas en la entrada pública.
- [x] Ejecutar los tres controles con modelos reales, revisar visualmente cada salida y corregir fallos del recorrido.
- [x] Verificar la integración, revisión Astra y publicar commits del resultado.

Límites iniciales: 32 parámetros, 64 componentes, 128 restricciones, 128 detalles y profundidad de expresiones 8. Compartir parámetros evita repetir espesores y premisas en cada pieza. Se reutilizan renderer/primitivas existentes cuando sean adecuados; no se amplían histórico económico, calibración PDF, 3D ni despliegue en esta fase.

Evidencia y límites de los controles: [verificación real](../../VERIFICACION_CAD_COMPLETION_2026-11-14.md). Los checks completados indican implementación y revisión ejecutadas; no equivalen a una precisión industrial demostrada ni a PASS en todos los criterios de referencia.
