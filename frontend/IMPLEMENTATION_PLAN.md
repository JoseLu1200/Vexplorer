# Interfaz completa de demo — plan de implementación

> **Para agentes:** ejecutar cada tarea con TDD y mantener `team/agente_frontend.md` al día. No delegar ni modificar rutas fuera de `frontend/`.

**Objetivo:** construir la interfaz JS y HTML en español que conecta carga, plano 2D, evidencia, propuestas, revisión de montaje, histórico, estimación, exportaciones y traza con la API real.

**Arquitectura:** aplicación web estática sin framework ni dependencias de ejecución. Módulos ES separan cliente HTTP, estado, adaptación de datos y componentes DOM. El visor genera SVG propio desde puntos numéricos validados y usa IDs canónicos para selección; nunca inserta markup del plano.

**Stack:** HTML semántico, CSS, JavaScript ES modules, SVG seguro y `node:test` para lógica y DOM mínimo inyectable.

**Especificación:** `frontend/UX_SPEC.md`, contrato Pydantic 0.2 acordado por A/B y rutas que comunique B.

## Restricciones globales

- Solo se consumen payloads reales del backend; los fixtures de test quedan bajo `frontend/tests/fixtures/` y se rotulan como sintéticos.
- No existe fallback con resultado prefijado.
- `geometry_only` funciona sin proveedor; `live` y replay dependen de capacidades reales.
- Observado, calculado, hipótesis y confirmado por persona permanecen separados.
- Cantidad, espesor y unidades desconocidos se muestran literalmente como desconocidos.
- El texto del DXF se trata como datos y nunca se inserta como HTML.
- No se añaden dependencias complejas ni recursos remotos necesarios para la demo.
- El servidor FastAPI de B sirve `frontend/` para un único comando de arranque.

## Riesgos que deben quedar probados

1. Payload parcial o en revisión: conserva plano y evidencia aunque no haya piezas.
2. Unidad desconocida: usa `source_points` y no muestra valores con sufijo mm.
3. Texto hostil del DXF: aparece literalmente y no crea elementos DOM.
4. Evento SSE duplicado o fuera de orden: no duplica la traza y detecta saltos.
5. Revisión obsoleta: informa conflicto, recarga instantánea y no anuncia confirmación.

---

### Tarea 1: Estado, contrato de cliente y shell

**Archivos:**
- Crear: `frontend/package.json`
- Crear: `frontend/index.html`
- Crear: `frontend/styles.css`
- Crear: `frontend/api/client.js`
- Crear: `frontend/core/state.js`
- Crear: `frontend/core/format.js`
- Crear: `frontend/tests/state.test.js`
- Crear: `frontend/tests/client.test.js`

**Interfaces:**
- `createApiClient({fetchImpl, eventSourceFactory})`
- `createStore(initialState)` con `getState`, `subscribe` y `dispatch`
- `formatKnown(value, unit)` y `formatSourceClass(origin)`

- [ ] Escribir pruebas de transiciones vacío, carga, parcial, error y terminal; observar fallo por módulos ausentes.
- [ ] Implementar store y formateo mínimo; ejecutar pruebas hasta verde.
- [ ] Escribir pruebas del cliente con sobres de éxito/error, descarga y cabeceras de idempotencia; observar fallo.
- [ ] Implementar cliente con rutas exactas comunicadas por B y errores tipados; ejecutar suite.
- [ ] Crear shell semántico, tokens CSS, estados de botones y vista inicial sin datos incrustados.
- [ ] Commit `frontend: crear shell y cliente API`.

### Tarea 2: Visor 2D, tabla y evidencia vinculadas

**Archivos:**
- Crear: `frontend/components/DrawingViewer.js`
- Crear: `frontend/components/PartsTable.js`
- Crear: `frontend/components/EvidencePanel.js`
- Crear: `frontend/core/drawing.js`
- Crear: `frontend/tests/drawing.test.js`
- Crear: `frontend/tests/traceability.test.js`

**Interfaces:**
- `normaliseDrawing(extraction)` devuelve primitivas seguras y unidad de coordenadas.
- `selectionForComponent(component, drawing)` devuelve conjuntos de IDs de contorno, entidad y evidencia.
- `renderDrawingViewer(root, model, callbacks)` y componentes equivalentes reciben nodos y datos, no HTML libre.

- [ ] Escribir prueba de unidad desconocida y puntos fuente; observar fallo.
- [ ] Implementar normalización y encuadre SVG; ejecutar prueba.
- [ ] Escribir prueba de selección bidireccional por IDs, incluyendo tres vistas de una pieza; observar fallo.
- [ ] Implementar selección y render de tabla/evidencia; ejecutar pruebas.
- [ ] Escribir prueba XSS con texto DXF hostil; comprobar que solo se crea un nodo de texto.
- [ ] Implementar textos seguros, navegación por teclado y estados vacíos/error.
- [ ] Commit `frontend: enlazar plano piezas y evidencias`.

### Tarea 3: Traza SSE y revisión humana

**Archivos:**
- Crear: `frontend/components/TracePanel.js`
- Crear: `frontend/components/ReviewPanel.js`
- Crear: `frontend/core/events.js`
- Crear: `frontend/tests/events.test.js`
- Crear: `frontend/tests/review.test.js`

**Interfaces:**
- `createEventLedger(runId)` con `append(envelope)` y detección de duplicado/salto.
- `buildReviewPayload(snapshot, formValues)` usa la revisión base y campos permitidos del contrato.
- `renderReviewPanel` presenta escenarios incompatibles y exige motivo antes de confirmar.

- [ ] Escribir secuencia 1,2,2,3 y salto 1,3; observar fallo.
- [ ] Implementar ledger de eventos y mensajes de reconexión; ejecutar prueba.
- [ ] Escribir prueba de escenario ambiguo, campos desconocidos y motivo requerido; observar fallo.
- [ ] Implementar formulario y payload contractual sin `reviewer_id` del cliente; ejecutar prueba.
- [ ] Escribir caso `409 stale_result_revision`; implementar recarga sin sobrescritura y probar.
- [ ] Commit `frontend: registrar revisión y traza SSE`.

### Tarea 4: Histórico, estimación y exportaciones

**Archivos:**
- Crear: `frontend/components/ComparablesPanel.js`
- Crear: `frontend/components/EstimatePanel.js`
- Crear: `frontend/components/ExportPanel.js`
- Crear: `frontend/core/estimate.js`
- Crear: `frontend/tests/estimate.test.js`
- Crear: `frontend/tests/export.test.js`

**Interfaces:**
- `presentEstimate(apiEstimate)` conserva conceptos, tarifas, procedencia, moneda, horas, exclusiones y campos desconocidos sin recalcular totales.
- `downloadArtifact(response, filename)` usa nombre seguro y URL temporal revocable.

- [ ] Escribir prueba de comparable sintético rotulado y diferencias verificables; observar fallo.
- [ ] Implementar presentación de histórico sin score como certeza; ejecutar prueba.
- [ ] Escribir prueba de conceptos con tarifa desconocida, subtotal parcial y revisión exacta; observar fallo.
- [ ] Implementar estimación y exclusiones sin cálculo paralelo; ejecutar prueba.
- [ ] Escribir prueba de exportación ficha/traza, error sin resultado y nombre seguro; implementar y probar.
- [ ] Commit `frontend: mostrar estimación y exportaciones`.

### Tarea 5: Integración, accesibilidad y recorrido real

**Archivos:**
- Crear: `frontend/app.js`
- Crear: `frontend/tests/app.test.js`
- Modificar: `frontend/index.html`
- Modificar: `frontend/styles.css`
- Modificar: `team/agente_frontend.md`

**Interfaces:**
- `bootApp({document, apiClient})` conecta carga, ejecución, snapshot, SSE, selección, revisión y salida.

- [ ] Escribir prueba de recorrido geometry only desde carga hasta snapshot parcial; observar fallo.
- [ ] Implementar orquestación mínima y polling de datos que aún no existan; ejecutar prueba.
- [ ] Probar capacidades: live no configurado y replay sin grabación permanecen deshabilitados con explicación.
- [ ] Ejecutar `npm test` y registrar salida real.
- [ ] Arrancar FastAPI de B y recorrer en navegador un DXF real o fixture servido por el backend; comprobar consola, escritorio y móvil.
- [ ] Corregir cualquier defecto mediante prueba roja antes de código.
- [ ] Actualizar registro con comandos, resultados y límites.
- [ ] Commit `frontend: completar recorrido integrado de demo`.

