# Agente frontend — demo local

Identidad: agente de IA frontend; no representa a una persona. Autorización: solicitud explícita del usuario del 2026-11-13.

## Rol y alcance

- Persona C del equipo: interfaz web en español para la demo.
- Propiedad exclusiva de `frontend/` y de este archivo.
- Consume contratos y endpoints acordados por A/B; no modifica `backend/`, `contratos/` ni archivos de otros integrantes.
- Coordina con A la procedencia geométrica del visor y con B la API, SSE, revisiones, exportaciones y servicio estático.

## Tarea actual

Implementar el recorrido acotado `mounted_orthographic_views` para la familia `rectangular_table_v1`: conservar la fuente DXF, comparar propuesta generativa y baseline de catálogo, revisar componentes e incógnitas, y consultar planos derivados generales, por pieza y de corte con costes explicados. Se mantiene disponible el recorrido 0.4 de piezas separadas y el legado de estantería.

## Decisiones

- Prioridad al plano 2D y a la trazabilidad; 3D es una vista técnica enlazada y nunca sustituye evidencia ausente.
- Estética de cuaderno técnico industrial, con información densa pero jerarquía clara y alto contraste.
- Las clases `observado`, `calculado`, `hipótesis` y `confirmado por una persona` se muestran separadas visual y semánticamente.
- La selección se conserva por IDs estables de API, nunca por índice de tabla.
- El texto procedente del DXF se renderiza con APIs de texto seguro; nunca se inserta como HTML.
- `geometry_only` funciona sin proveedor; `live` solo aparece habilitado con proveedor real configurado; `recorded_replay` solo con grabación real.

## Estado

Fase 0.5 iniciada en `feat/table-frontend` desde `main` `164356b`. La especificación y el plan de mesa están aprobados en `4ba95e6`; el contrato A/B 0.5 todavía debe congelarse antes de implementar adaptadores dependientes de sus campos. Análisis UX y contraste del frontend existente en curso.

## Dependencias / avisos

- Pendiente aviso de B con modelos Pydantic y rutas exactas 0.5 para programa generativo, baseline de catálogo, revisión, manifiesto de láminas, SVG/DXF y costes. No se mantendrá un esquema paralelo en el navegador.
- Geometría ha confirmado que `unknown|conflict` conserva `value_mm=null` y que medidas, componentes y colocaciones llevarán IDs de medición, vista, evidencia, bindings y operandos; faltan los nombres definitivos.
- Contrato 0.2 acordado por A/B y consumido por IDs estables de entidad, contorno, evidencia y propuesta.
- Three.js queda fijado en `0.187.0`; `npm ci` genera solo `three.module.js`, `three.core.js`, `OrbitControls.js` y la licencia bajo `frontend/vendor/`, sin CDN ni publicación de `node_modules`.
- FastAPI sirve `frontend/` desde el mismo origen; las rutas de recursos son `/styles.css`, `/app.js` y módulos relativos.
- El frontend no incluirá mocks prefijados que se presenten como inferencia. Los tests podrán usar fixtures contractuales explícitos y la UI mostrará estados vacíos o errores cuando la API no aporte datos.

## Verificación

- `cd frontend; npm test`: 46 pruebas, 46 aprobadas, 0 fallos en el último ciclo local, incluidas respuestas/rechazos diferidos que no pueden pisar una sesión nueva.
- `node --check app.js` y `node --check components/SceneViewer.js`: sin errores de sintaxis.
- Smoke HTTP en `http://127.0.0.1:8766`: `/`, `app.js`, `three.module.js`, `three.core.js` y `OrbitControls.js` responden 200. El visor 3D se importa dinámicamente para que un fallo WebGL no bloquee 2D.
- Navegador real en `http://127.0.0.1:8765`: servicio y recursos cargados; upload DXF real; 3 vistas y 15 paths; 4 cotas observadas; tabla de hipótesis; dos escenarios incompatibles; campos de revisión; comparables sintéticos y traza visibles.
- El coordinador verificó en navegador la revisión 2 con balda calculada a 864 mm y estimación total 127,84 EUR. Durante esa revisión se detectaron y corrigieron overlay `hidden`, estado de carga terminal, procedencia por campo y detalle de tarifas/factores.
- El coordinador verificó en navegador real la reconstrucción 3D de seis ocurrencias con órbita/captura sin bloqueo, las cotas legibles durante zoom y la biblioteca geométrica/semántica con grupos explicados.
- No se probó modo `live`: no hay proveedor real configurado. Replay permanece deshabilitado porque no existe grabación real.
