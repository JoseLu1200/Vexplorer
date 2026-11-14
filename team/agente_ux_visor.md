# Agente UX visor 3D

## Identidad y autorización

- Identidad: agente de IA del visor; no representa a una persona.
- Autorización: delegación explícita del swarm autorizado por el usuario el 2026-11-14.
- Rol: corregir el reflow y ciclo de vida del visor 3D sin modificar contratos ni el shell compartido.

## Alcance y reservas

- Propiedad exclusiva de esta tarea: `frontend/components/SceneViewer.js`, `frontend/tests/scene.test.js`, nuevos tests asociados y este registro.
- Solo lectura: `frontend/app.js`, `frontend/styles.css`, `frontend/index.html` y resto del producto.
- Se preservará el cambio local previo de sincronización de tema en `SceneViewer.js`.

## Tarea de la sesión

- Reproducir que cambios de tamaño del contenedor sin evento `window.resize` dejan el canvas y la cámara desincronizados.
- Corregir reflow al colapsar/expandir rail y al ocultar/mostrar el panel, con limpieza completa de listeners, observadores y recursos WebGL.
- Cubrir el comportamiento con pruebas RED→GREEN y ejecutar la suite frontend.

## Dependencias / avisos

- Si el arreglo exige tocar el shell o estilos, se coordinará con el propietario de interfaz; no se editarán unilateralmente.
- No se cambian contratos ni payloads.
- QA posterior: el rótulo provisional vive en `core/ui.js` y el reset de controles de escena en `app.js`, ambos propiedad de interfaz funcional. La causa exacta y el cambio sugerido se transfirieron a `/root/functional_ui`; no se invadieron esos archivos.

## Estado

- Implementación terminada dentro del alcance propio.
- Causa confirmada: el visor escuchaba solo `window.resize`; el rail y la visibilidad alteran el rectángulo del contenedor sin emitir ese evento, dejando buffer y proyección con el tamaño anterior.
- `ResizeObserver` sigue ahora el contenedor real. Un rectángulo 0×0 conserva la última proyección válida y la siguiente notificación visible actualiza buffer, aspect ratio y render.
- `dispose()` desconecta el observador, elimina listeners de puntero/controles/tema y libera renderer/contexto WebGL.
- Se preservó intacta la sincronización local previa de tema claro/oscuro.

## Pruebas y revisión

- RED 1: `node --test tests/scene.test.js` falló porque faltaba `observeContainerSize`.
- GREEN 1: focal de escena, 5/5 aprobadas.
- RED 2: focal falló porque faltaba `resizeRendererToContainer` para oculto→visible.
- GREEN 2: `node --test tests/scene.test.js` → 6/6 aprobadas.
- Suite frontend: `npm test` → 148 aprobadas, 1 fallo ajeno en `ui-contract.test.js` por una regla responsive ausente en el `styles.css` modificado concurrentemente; el fallo no toca archivos propios y se avisó a coordinación.
- No se hizo QA de navegador para no interferir con los contextos Playwright/Chrome reservados por coordinación; las transiciones de tamaño y visibilidad quedan cubiertas con pruebas deterministas.
- Seguimiento QA: `sceneContextLabel` ya pasa el caso `needs_review` como provisional. La prueba RED concurrente `reset clears provisional 3D controls before a pending document is shown` confirma que `resetRunUi()` deja visibles `#explode-control`/`#scene-warning`; interfaz funcional está implementando el GREEN.
