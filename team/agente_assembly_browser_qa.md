# Agente assembly browser QA — montaje general

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA `assembly_browser_qa`; no representa a una persona.
- Rol: verificación de navegador del montaje general integrado y regresión del recorrido de mesa.
- Archivo creado o designado explícitamente: encargo de `/root` del 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: comprobar en navegador el montaje por ocurrencia del run complejo y la regresión del run de mesa, con capturas, consola y evidencia reproducible.
- Referencias: `docs/superpowers/specs/2026-11-14-general-assembly-design.md` y `docs/demo-local-2026-11-14.md`.
- Estado: en curso; implementación frontend/runtime concurrente todavía no integrada en el servicio local.

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

- Bloqueo transitorio: integración todavía en curso y sesión DevTools central no transferible.
- No hay afirmación de éxito hasta observar el servicio reiniciado y guardar la evidencia final.
- Reservas liberadas: no.
