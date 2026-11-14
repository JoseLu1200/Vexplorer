# Plan de implementación: completar CAD 2D

Fuente: [encargo y diseño](../specs/2026-11-14-cad-completion.md).

- [ ] Congelar un contrato compacto de construcción y dimensión observada/deducida/estimada, con ejemplo completo compartido entre agentes.
- [ ] Resolver parámetros y operaciones; validar cierres, espesores, vanos y cantidades sin modificar observaciones.
- [ ] Extender el harness nativo para interpretar el mueble, completar piezas y detalles, estimar faltantes y corregir contradicciones automáticamente.
- [ ] Producir lista provisional con valores estimados explícitos y planos SVG/DXF acotados por pieza.
- [ ] Conectar la interpretación, los planos y la explicación priorizada en la interfaz 2D y API persistente.
- [ ] Crear tres controles propios de vistas montadas y referencias por escenarios, sin respuestas en la entrada pública.
- [ ] Ejecutar los tres controles con modelos reales, revisar visualmente cada salida y corregir fallos del recorrido.
- [ ] Verificar la integración, revisión Astra y publicar commits del resultado.

Límites iniciales: 32 parámetros, 64 componentes, 128 restricciones, 128 detalles y profundidad de expresiones 8. Compartir parámetros evita repetir espesores y premisas en cada pieza. Se reutilizan renderer/primitivas existentes cuando sean adecuados; no se amplían histórico económico, calibración PDF, 3D ni despliegue en esta fase.
