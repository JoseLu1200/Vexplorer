# Agente de hallazgos frontend

## Identidad y autorización

- Identidad: agente de IA de interfaz; no representa a una persona.
- Autorización: delegación explícita del coordinador `/root` tras la autorización del usuario del 2026-11-14.
- Rol: corregir navegación por capacidades, persistencia resiliente, protección de revisión, proyectos recientes y UX durable de cola/cancelación.

## Alcance y reservas

- Propiedad frontend: `frontend/index.html`, `frontend/styles.css`, `frontend/app.js`, `frontend/api/client.js`, módulos `frontend/core/` necesarios y pruebas unitarias/contractuales frontend.
- Coordinación browser: este agente mantiene `frontend/package.json` y `frontend/package-lock.json`; `/root/browser_ci` mantiene `frontend/e2e/**`, configuración Playwright y CI.
- Backend limitado: helper de capacidad en `backend/app/semantic_explorer/router.py` y adición estrecha a `/api/v1/config`, solo tras coordinar con escritores de `backend/app/main.py`.
- Sin propiedad: rutas, persistencia o autorización backend de trabajos/proyectos; corresponden a `/root/jobs` y `/root/security`.
- Sin commits, push ni despliegue.

## Plan de implementación

1. Añadir pruebas RED de almacenamiento/URL resilientes y aplicar un adaptador único con memoria.
2. Añadir pruebas RED para capacidad del explorador y mostrar enlace o guía de habilitación.
3. Añadir pruebas RED para cambios de revisión sin guardar y proteger acciones destructivas.
4. Añadir pruebas RED y UI separada de proyectos/ejecuciones recientes.
5. Añadir pruebas RED para posición de cola, cancelación durable y estado terminal `cancelled`.
6. Ejecutar suite frontend, comprobaciones de sintaxis/diff y las pruebas backend focales que correspondan.

## Dependencias / avisos

- `/root/jobs`: contrato de `GET /projects`, `GET /executions`, campos de cola y `POST /jobs/{id}/cancel`.
- `/root/security`: actor scope y envolventes definitivas de listas.
- `/root/browser_ci`: selectores estables `#semantic-explorer-link`, `#semantic-explorer-guidance`, `#review-form[data-dirty]`, `#job-cancel` y `#job-status`.
- Cambio de `contratos/`: no aplica.

## Estado

- Implementación terminada y pendiente únicamente de la revisión final coordinada.
- El explorador semántico se anuncia desde la capacidad real de la instancia; el enlace permanece oculto y muestra guía cuando el servicio no está inicializado.
- Persistencia de run/job, tema y rail usa un adaptador resiliente con memoria, URL prioritaria y tolerancia a getters, cuotas y `replaceState` bloqueados.
- Las revisiones exponen `data-dirty`, recalculan antes de `beforeunload` y protegen carga, nueva ejecución, recientes, Biblioteca, precedentes, marca y explorador.
- Proyectos y ejecuciones recientes tienen panel propio, paginación y apertura/seguimiento sin reenvío del trabajo.
- Al terminar correctamente un trabajo, la actividad reciente se refresca después del run y la traza; el resultado aparece sin recargar y se abre por su `run_id` sin crear otro job.
- Cola y cancelación durable muestran posición, solicitud pendiente y terminal `cancelled`; el trabajo cancelado no se restaura como activo.
- Guardado semántico frontend usa exclusivamente `embeddinggemma2`.
- `@playwright/test` está fijado en `1.65.1` y `npm run test:browser` es el contrato del lane browser.

## Pruebas y revisión

- Baseline previo: `npm test` → 260/260.
- RED focal: 8 fallos esperados en storage/jobs/client/UI y 1 fallo esperado del guard de revisión antes de implementar.
- Suite frontend final: `npm test` → 273/273.
- Browser aislado final: `npm run test:browser` → 6/6, incluido restaurar una ejecución reciente sin crear otro job, exit 0.
- Backend focal: `.venv\\Scripts\\python.exe -m pytest backend/tests/test_semantic_explorer.py backend/tests/test_job_lifecycle.py -q` → 35 passed, 1 warning deprecado de Starlette/httpx.
- Sintaxis: `node --check app.js` y `node --check core/review.js` → exit 0.
- Integridad: `git diff --check` sobre frontend, explorador y registro → exit 0.

## Bloqueos y cierre

- Bloqueos: ninguno propio.
- Pendiente: lectura final de `/root/reviewer` y verificación integral del coordinador.
- No se hicieron commits, push ni despliegue.
