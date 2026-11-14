# Demo local y evaluación del mueble complejo

Servicio con perfil production: https://localhost:8765 (HTTPS local, no despliegue público). Datos persistentes en `.runtime/localhost-production/data`. Arranque: `powershell -ExecutionPolicy Bypass -File tools/start_local_demo.ps1`; añadir `-Restart` para reiniciar exclusivamente este servicio. El certificado local preparado es temporal.

## Abrir la demo compleja

https://localhost:8765/?run=run-9eb5e3aca8a04331ac0b0d3e5e2f2f40

1. Pulsa **Fuente → Todas**, **Sin orientar** y **CAD original** para inspeccionar el dibujo original.
2. Pulsa **Esquema general**: carga el SVG de la revisión 1. Usa **SVG** o **DXF** para descargarlo.
3. Pulsa **3D** en la barra de vistas. Si no aparece, desplaza horizontalmente esa barra. Se muestra una representación por tipo de pieza, distribuida para inspección; no es un montaje reconstruido.
4. Pulsa una fila de la tabla, por ejemplo **Laterales**: se selecciona la pieza y se abre **01 Inspector** con medidas, cantidad y evidencia. También funciona Tab y Espacio/Intro. En 3D se resalta el tipo correspondiente.
5. Prueba **Acercar**, **Alejar**, **Encajar** y **Reiniciar**. Puedes arrastrar la vista 3D para orbitar.
6. Abre **02 Revisar**: consulta las comprobaciones de máquina y las incógnitas. **Corrección humana avanzada** permite editar; no registres como confirmado algo que no has comprobado. **Nueva ejecución con auto-revisión** inicia otra llamada real al modelo.
7. Abre **03 Biblioteca**. En **Mostrar procedencia**, elige **Fuentes públicas publicadas**: hay 19 registros, 4 con presupuesto/coste y 19 con horas. **Buscar similares** y **Agrupar por descriptor** funcionan, pero la biblioteca preparada contiene mesas: no demuestra comparabilidad con el armario.
8. Abre **04 Coste → Consultar escenarios**. Los importes son hipótesis condicionales, en la moneda de la fuente. Los comparables de mesas/pufs no bastan para presupuestar este armario. **Estimar desde histórico confirmado** permanece deshabilitado porque faltan datos confirmados.
9. Descarga **BOM CSV**, **BOM JSON**, **Esquema SVG** y **Esquema DXF**. La BOM conserva su estado incompleto. **Traza** abre el registro de ejecución.
10. Recarga la URL: la propuesta y revisión permanecen guardadas.

**Por pieza** y **Despiece** están deshabilitados en este recorrido general: no hay láminas derivadas de esos tipos. No se presentan como funcionalidades completadas. La selección individual se puede probar en 3D; las láminas por pieza sí están disponibles en el recorrido de mesa siguiente.

## Repetir desde archivo

Archivo exacto: `C:\Users\Álvaro Schwiedop\Desktop\KriptaStudios\1hack\plankassembly_adapter_blind20_v2\plank-030.dxf`.

Pulsa **Cargar plano**, elige ese archivo; en **Tipo de plano** selecciona **Mueble general · propuesta revisable**; en **Modo de análisis**, **Agente en vivo**; pulsa **Abrir** y espera a que termine la revisión. Se usa un modelo real y el resultado puede variar. Las referencias privadas de evaluación no se proporcionan al agente.

## Juicio sobre el caso complejo

Mueble de 2400 mm de altura con laterales, horizontales, estantes de distinto fondo, dos traseras, frentes y zócalos. DXF de 192 entidades. El análisis produjo 10 tipos y 16 piezas físicas. Se contrastaron dimensiones ortogonales ordenadas por pieza contra la referencia después de congelar la primera salida: **16/16 coincidencias dentro de 1 mm**, error máximo aproximado **0,000352 mm**. Ese decimal refleja precisión numérica del fixture, no una tolerancia industrial. La segunda ejecución repitió las 16 coincidencias.

La primera ejecución falló al registrar la revisión porque las evidencias del binding de cantidad no figuraban en el resumen del componente. Corregido con una regresión que también rechaza referencias inventadas. La segunda ejecución terminó con propuesta 1/revisión 1, estado `reviewed_incomplete`, revisión de máquina real. No se convirtió ninguna hipótesis en confirmación humana.

**Valoración:** buen resultado en extracción de medidas/cantidades para este caso; insuficiente para fabricación automática. No se verificaron ubicación montada, colisiones reales, uniones, mecanizados, materiales ni herrajes. El 3D es un despiece esquemático, no evidencia de montaje correcto. La estimación económica no es fiable para este caso con la biblioteca actual. Un solo caso no mide la fiabilidad general del sistema.

Evidencia local: `.runtime/localhost-production/complex-evaluation/` contiene salidas originales, revisión, respuestas del crítico y métricas. Primera ejecución preservada: `run-e6ab7332c9bf4775b14013f3d91a3ecb`.

## Mesa preparada: láminas y coste persistente

https://localhost:8765/?run=run-161fc0b9bf7c46f499ddf84abe105d9b

- Pulsa una fila **Tapa** o **Soportes laterales**: abre la lámina exacta y el inspector. En **3D**, resalta las piezas correspondientes.
- Prueba **Esquema general**, **Por pieza**, **Despiece**, descargas SVG/DXF y ficha de corte.
- **04 Coste**: demo de tarifas sintéticas, 180,32 EUR de coste y 225,40 EUR de venta con margen 20 %. Recarga: conserva selección de cantos, operación, 1,5 horas y margen. No es un presupuesto real.
- **03 Biblioteca → Modo de comparación → Semántico · modelo real → Buscar similares**. Hay 4 registros almacenados, 2 diseños únicos, embeddings reales `text-embedding-3-small`, 256 dimensiones. Duplicados identificados; no se anuncian como cuatro diseños distintos.

Archivo de mesa: `C:\Users\Álvaro Schwiedop\Desktop\KriptaStudios\1hack\Vexplorer\data\planos_demo\mesa_demo_001.dxf`.

## Demo de estimación con embeddings

https://localhost:8765/?run=run-564b920c178b4603bd98c86c65032557

Abre **04 Coste**, selecciona **Embeddings reales** y pulsa **Estimar desde histórico confirmado**. Se verificó un resultado de 195,52 PLN. El objetivo es un escenario expresamente SIMULADO con medidas de demo y condiciones materiales/económicas copiadas de una referencia publicada; no es una valoración real del armario ni un precio en EUR. Permite demostrar la recuperación semántica real sin ocultar los supuestos.

Los históricos preparados proceden de `public_furniture_history_2026-11-14/historical_import.json` y `public_furniture_hours_2026-11-14/historical_import.json`, directorios hermanos del repositorio. Ya están importados; no necesitas repetirlo.

## Verificación y límites

- 175 pruebas frontend y 42 pruebas backend focalizadas pasan. Una advertencia de deprecación Starlette/httpx, sin fallos.
- Navegador: fuente, esquema, 3D, selección por clic/teclado, zoom, encajar, reiniciar, cuatro paneles, tema, traza, consulta de escenarios, búsqueda y agrupación. Sin errores de consola en este recorrido.
- SVG, DXF, BOM CSV y BOM JSON del caso complejo: HTTP 200 y contenido no vacío.
- No se hizo una cobertura exhaustiva de toda combinación de controles ni una prueba de carga. Importación DWG/PDF, normalización de páginas y exportación de todos los formatos no quedan certificadas por este ensayo DXF.
- Se corrigieron además persistencia de costes, replay de mesa, referencias del proponente general y errores 500 al intentar guardar/buscar una mesa sin revisión. Las validaciones siguen impidiendo publicar o presupuestar una revisión no aceptada.
- Los avisos de revisión no son fallos que deban ocultarse: ahora la vista general puede mostrar piezas provisionales y explica su estado. No se afirma que se hayan evaluado colisiones sin geometría de montaje respaldada.
