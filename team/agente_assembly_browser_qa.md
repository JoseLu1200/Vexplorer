# Agente assembly browser QA — montaje general

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA `assembly_browser_qa`; no representa a una persona.
- Rol: verificación de navegador del montaje general integrado y regresión del recorrido de mesa.
- Archivo creado o designado explícitamente: encargo de `/root` del 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: comprobar en navegador el montaje por ocurrencia del run complejo y la regresión del run de mesa, con capturas, consola y evidencia reproducible.
- Referencias: `docs/superpowers/specs/2026-11-14-general-assembly-design.md` y `docs/demo-local-2026-11-14.md`.
- Estado: completado con evidencia; no existe un montaje live aceptado, por lo que el candidato de 16 ocurrencias se verificó únicamente en el modo diagnóstico rechazado y claramente rotulado.

## Alcance y reservas

- Archivos editables: este registro y `.runtime/assembly-verification/browser-*`.
- Producto en modo solo lectura; no se modifica frontend, backend, contratos ni datos persistidos.
- No se inicia ninguna llamada real al modelo ni se pulsa el reintento de montaje sin coordinación.

## Hecho en el último bloque

- Leí criterios de aceptación, recorrido local y código actual del visor.
- Confirmé que el código visible al inicio seguía usando el fallback `generalSceneForViewer`: una vista por tipo, cuadrícula esquemática y sin orientación de ocurrencias.
- Intenté consumir la pestaña Chrome DevTools entregada (`pageId=2`), pero el cliente de este agente no puede adjuntarse al perfil compartido mientras el proceso del agente raíz lo mantiene abierto. Se notificó a `/root`; la ejecución Chrome se hará centralmente sin cerrar el navegador compartido.
- Preparé el guion exacto en `.runtime/assembly-verification/browser-qa-plan.md`.

## Dependencias / avisos

- Depende de `assembly_viewer`, `assembly_core` y `assembly_runtime` para la integración final y el reinicio controlado del servicio.
- `/root` conserva la sesión Chrome y ejecutará los pasos/capturas centralmente si el perfil no puede transferirse.
- Se avisó a `assembly_viewer` de que comunique las etiquetas y el contrato final del visor.

## Pruebas y revisión

| Caso | Evidencia | Resultado actual | Pendiente |
|---|---|---|---|
| Preparación del run complejo | inspección de `frontend/core/scene.js`, `frontend/components/SceneViewer.js`, `frontend/app.js` | baseline aún esquemático al inicio del turno | repetir tras integración/reinicio |
| Acceso Chrome compartido | error literal de Chrome DevTools MCP sobre perfil ya en uso | bloqueo de cliente, no del producto | ejecución central por `/root` |
| Run complejo | `browser-complex-*` | pendiente | 16 ocurrencias, orientación, selección, cámara, despiece, persistencia, estados y consola |
| Run mesa | `browser-table-*` | pendiente | hojas/3D/selección/cámara/despiece/recarga y consola |

## Bloqueos y cierre

- Chrome DevTools no fue transferible entre agentes por el bloqueo del perfil compartido; la verificación final se ejecutó con Chromium Playwright aislado, sin cerrar ni modificar el navegador compartido.
- No se obtuvo ningún montaje live aceptado. `plank-030` rev4 conserva 16 colocaciones pero está correctamente rechazado; nunca se presenta como montaje validado. `plank-016` se abstuvo y el control sin unidades paró antes del proveedor.
- El modo diagnóstico opt-in muestra las 16 ocurrencias con `Z` como eje vertical mediante una única transformación global dextrógira; no altera cada pieza. El gabinete quedó vertical en captura.
- Salir vuelve al despiece esquemático; recargar mantiene el despiece y restablece eje `Y`. Incidencia menor: inmediatamente después de salir, el selector todavía muestra `Z` hasta recarga aunque el visor interno vuelve a `Y`.
- Reservas liberadas: sí.

## Evidencia final

| Caso | Resultado observado |
|---|---|
| Rechazo seguro plank-030 rev4 | `Montaje rechazado`; escena rechazada no se monta por defecto; BOM y esquema disponibles |
| Diagnóstico 16 ocurrencias | `Candidato rechazado · no validado · solo inspección · 16 ocurrencias`; banner `no usar para fabricar`; gabinete vertical con eje Z |
| Selección por ocurrencia | `shelves:1`, índice 1, inspector de instancia y agrupación con `Baldas interiores superiores` |
| Cámara/despiece | zoom, órbita y explosión cambian píxeles; desactivar explosión restaura exactamente la escena |
| Retorno/persistencia | botón vuelve al esquema; recarga conserva esquema y opt-in sin promover candidato |
| Errores agrupados | resumen español cerrado con 47 incidencias agrupadas; detalle técnico completo disponible al abrir |
| Mesa de regresión | 3 objetos; clic y teclado seleccionan Tapa/Soportes; órbita, zoom, explosión/restauración, láminas y recarga operativas |
| Control sin unidades | run `run-54cfb9b2022341b790b1615ad3a3387c`; `assembly_metric_scale_required`; 0 llamadas/0 herramientas; sin escena |
| Segundo mueble | run `run-dbf758e4fbcd4b19bff8552201a48d4a`; revisión terminal incompleta, 11 componentes; abstención de montaje |
| Consola/red | 0 errores de página, 0 requests fallidas, 0 HTTP >=400; solo avisos de rendimiento `ReadPixels` del Chromium headless |
| Suite frontend fresca | `npm test`: 192 passed, 0 failed |

Artefactos principales: `.runtime/assembly-verification/browser-rejected-diagnostic.json`, `browser-complex-rejected-16-world.png`, `browser-complex-rejected-instance-selected.png`, `browser-complex-rejected-summary-closed.png`, `browser-complex-rejected-summary-open.png`, `browser-complex-rejected-normal-restored.png`, `browser-complex-rejected-reload-normal.png`, `browser-probe.json`.
