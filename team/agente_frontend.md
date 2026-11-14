# Agente frontend — demo local

Identidad: agente de IA frontend; no representa a una persona. Autorización: solicitud explícita del usuario del 2026-11-13.

## Rol y alcance

- Persona C del equipo: interfaz web en español para la demo.
- Propiedad exclusiva de `frontend/` y de este archivo.
- Consume contratos y endpoints acordados por A/B; no modifica `backend/`, `contratos/` ni archivos de otros integrantes.
- Coordina con A la procedencia geométrica del visor y con B la API, SSE, revisiones, exportaciones y servicio estático.

## Tarea actual

Implementar el recorrido acotado `mounted_orthographic_views` para la familia `rectangular_table_v1`: conservar la fuente DXF, comparar propuesta generativa y baseline de catálogo, revisar componentes e incógnitas, y consultar planos derivados generales, por pieza y de corte con costes explicados. Se mantiene disponible el recorrido 0.4 de piezas separadas y el legado de estantería.

## Cierre privado de producción — 2026-11-14

- Identidad activa: agente C de IA frontend, autorizado por la delegación explícita del usuario para el servidor privado.
- Propiedad exclusiva de este bloque: `frontend/*` y este registro. No editaré backend, contratos, geometría ni archivos de otros agentes.
- Objetivo: integrar sesión e identidad del servidor, envío y recuperación de jobs mediante polling, revisiones protegidas contra respuestas obsoletas, historial de eventos consultable, economía real/demo trazable y accesibilidad de cajones/modales, preservando el diseño actual.
- Dependencias: B publicará el contrato exacto de auth/jobs; costes comunicará el delta económico A/B; geometría comunicará las confirmaciones humanas editables. Hasta entonces, las integraciones se implementan de forma aditiva y tolerante a capacidades ausentes.
- Restricciones: TDD JS, sin dependencias nuevas, sin commits y sin modificar el transporte backend. El servidor es autoritativo; cualquier fallback local será manual y visible.
- Estado: Task 4 implementada. Jobs recuperables, identidad de sesión, revisiones humanas corregibles, costes 0.6, accesibilidad del cajón y prefijo `/vexplorer/` integrados sin alterar el diseño base.
- Verificación: `cd frontend; npm test` → 100/100; checks de sintaxis de `app.js`, `api/client.js` y `core/table.js` → exit 0; smoke real autenticado/prefijado delegado al coordinador.
- Evidencia y límites: `.runtime/production/frontend-report.md`. No se desplegó, no se usó proveedor y no se hicieron commits.

## Decisiones

- Prioridad al plano 2D y a la trazabilidad; 3D es una vista técnica enlazada y nunca sustituye evidencia ausente.
- Estética de cuaderno técnico industrial, con información densa pero jerarquía clara y alto contraste.
- Las clases `observado`, `calculado`, `hipótesis` y `confirmado por una persona` se muestran separadas visual y semánticamente.
- La selección se conserva por IDs estables de API, nunca por índice de tabla.
- El texto procedente del DXF se renderiza con APIs de texto seguro; nunca se inserta como HTML.
- `geometry_only` funciona sin proveedor; `live` solo aparece habilitado con proveedor real configurado; `recorded_replay` solo con grabación real.

## Estado

Fase 0.5 implementada sobre el contrato A/B congelado: carga de mesa montada, ledger geométrico, programa de catálogo o generado, revisión explícita, planos derivados, costes por alcance y reconstrucción 3D conviven con piezas separadas 0.4 y legado. El smoke real del 2026-11-14 recorrió revisión 1→2, las cuatro láminas SVG/DXF, escena de tres ocurrencias y coste parcial versionado.

## Dependencias / avisos

- Contrato y runtime 0.5 consumidos con sus nombres definitivos. Los slots desconocidos que el programa marca `blocking:false` permanecen visibles en el ledger, pero no se solicitan como confirmaciones humanas.
- `unknown|conflict` conserva `value_mm=null`; medidas, componentes y colocaciones mantienen IDs de medición, vista, evidencia, bindings y operandos.
- Contrato 0.2 acordado por A/B y consumido por IDs estables de entidad, contorno, evidencia y propuesta.
- Three.js queda fijado en `0.187.0`; `npm ci` genera solo `three.module.js`, `three.core.js`, `OrbitControls.js` y la licencia bajo `frontend/vendor/`, sin CDN ni publicación de `node_modules`.
- FastAPI sirve `frontend/` desde el mismo origen; las rutas de recursos son `/styles.css`, `/app.js` y módulos relativos.
- El frontend no incluirá mocks prefijados que se presenten como inferencia. Los tests podrán usar fixtures contractuales explícitos y la UI mostrará estados vacíos o errores cuando la API no aporte datos.

## Verificación

- `cd frontend; npm test`: 82 pruebas aprobadas, 0 fallos en el último ciclo local, incluidas identidad de láminas, filtrado de slots no bloqueantes y curvas circulares tipadas.
- Smoke aislado en navegador contra `http://127.0.0.1:8768`: revisión 1→2, plano general, dos planos por componente, despiece, enlaces SVG/DXF, escena 3D y coste parcial de 126,32 EUR con tarifa explícita. Los GET opcionales de manifiesto/coste aún no generados devuelven 404 y el frontend los trata como estado vacío.
- Responsive comprobado en navegador a 1042 px y 501 px: sin solape ni ancho horizontal; todos los controles de carga permanecen accesibles.
- Planos derivados comprobados con SVG 1600×1541: zoom vectorial, pan, encaje y modo ampliado 992×452; Escape restaura la vista compacta. El ledger 2D dibuja círculos y arcos exactos desde centro/radio/ángulos publicados, sin convertir puntos auxiliares en cuerdas.

- `cd frontend; npm test`: 46 pruebas, 46 aprobadas, 0 fallos en el último ciclo local, incluidas respuestas/rechazos diferidos que no pueden pisar una sesión nueva.
- `node --check app.js` y `node --check components/SceneViewer.js`: sin errores de sintaxis.
- Smoke HTTP en `http://127.0.0.1:8766`: `/`, `app.js`, `three.module.js`, `three.core.js` y `OrbitControls.js` responden 200. El visor 3D se importa dinámicamente para que un fallo WebGL no bloquee 2D.
- Navegador real en `http://127.0.0.1:8765`: servicio y recursos cargados; upload DXF real; 3 vistas y 15 paths; 4 cotas observadas; tabla de hipótesis; dos escenarios incompatibles; campos de revisión; comparables sintéticos y traza visibles.
- El coordinador verificó en navegador la revisión 2 con balda calculada a 864 mm y estimación total 127,84 EUR. Durante esa revisión se detectaron y corrigieron overlay `hidden`, estado de carga terminal, procedencia por campo y detalle de tarifas/factores.
- El coordinador verificó en navegador real la reconstrucción 3D de seis ocurrencias con órbita/captura sin bloqueo, las cotas legibles durante zoom y la biblioteca geométrica/semántica con grupos explicados.
- No se probó modo `live`: no hay proveedor real configurado. Replay permanece deshabilitado porque no existe grabación real.
