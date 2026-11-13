# Agente frontend — demo local

Identidad: agente de IA frontend; no representa a una persona. Autorización: solicitud explícita del usuario del 2026-11-13.

## Rol y alcance

- Persona C del equipo: interfaz web en español para la demo.
- Propiedad exclusiva de `frontend/` y de este archivo.
- Consume contratos y endpoints acordados por A/B; no modifica `backend/`, `contratos/` ni archivos de otros integrantes.
- Coordina con A la procedencia geométrica del visor y con B la API, SSE, revisiones, exportaciones y servicio estático.

## Tarea actual

Construir una interfaz JS/HTML local para la familia de estantería rectangular que permita cargar DXF, inspeccionar vistas 2D y evidencia, revisar propuestas, registrar una decisión humana de montaje ambiguo, consultar un histórico sintético pequeño, revisar una estimación provisional por conceptos y exportar ficha y traza.

## Decisiones

- Prioridad al plano 2D y a la trazabilidad; no se dedicará el recorrido principal a 3D.
- Estética de cuaderno técnico industrial, con información densa pero jerarquía clara y alto contraste.
- Las clases `observado`, `calculado`, `hipótesis` y `confirmado por una persona` se muestran separadas visual y semánticamente.
- La selección se conserva por IDs estables de API, nunca por índice de tabla.
- El texto procedente del DXF se renderiza con APIs de texto seguro; nunca se inserta como HTML.
- `geometry_only` funciona sin proveedor; `live` solo aparece habilitado con proveedor real configurado; `recorded_replay` solo con grabación real.

## Estado

Implementación completa e integrada por el coordinador en `demo/first-executable`. La UI consume el contrato canónico 0.2, muestra propuestas de los dos escenarios de montaje, registra la revisión humana, consulta comparables y presenta la estimación y exportaciones del backend.

## Dependencias / avisos

- Contrato 0.2 acordado por A/B y consumido por IDs estables de entidad, contorno, evidencia y propuesta.
- FastAPI sirve `frontend/` desde el mismo origen; las rutas de recursos son `/styles.css`, `/app.js` y módulos relativos.
- El frontend no incluirá mocks prefijados que se presenten como inferencia. Los tests podrán usar fixtures contractuales explícitos y la UI mostrará estados vacíos o errores cuando la API no aporte datos.

## Verificación

- `cd frontend; npm test`: 28 pruebas, 28 aprobadas, 0 fallos en el último ciclo local.
- Navegador real en `http://127.0.0.1:8765`: servicio y recursos cargados; upload DXF real; 3 vistas y 15 paths; 4 cotas observadas; tabla de hipótesis; dos escenarios incompatibles; campos de revisión; comparables sintéticos y traza visibles.
- El coordinador verificó en navegador la revisión 2 con balda calculada a 864 mm y estimación total 127,84 EUR. Durante esa revisión se detectaron y corrigieron overlay `hidden`, estado de carga terminal, procedencia por campo y detalle de tarifas/factores.
- No se probó modo `live`: no hay proveedor real configurado. Replay permanece deshabilitado porque no existe grabación real.
