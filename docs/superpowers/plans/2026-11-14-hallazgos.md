# Hallazgos y recuperación de proyectos — Implementation Plan

> **For agentic workers:** usar superpowers:subagent-driven-development, reparto paralelo solicitado por el usuario, revisión independiente Astra.

**Goal:** resolver seis defectos auditados y añadir recientes, protección de revisión, E2E en CI y medición de utilidad.

**Architecture:** conservar FastAPI, SQLite y frontend JS; propietarios durables y autorización uniforme; cancelación cooperativa y concurrencia acotada. EmbeddingGemma 2 con identidad de espacio completa; almacenamiento navegador opcional.

**Tech Stack:** Python, FastAPI, SQLite, Pydantic, JavaScript, Node tests, pytest y Playwright.

**Spec:** petición del usuario de esta sesión, registrada en `team/agente_hallazgos_coordinacion.md`, y decisiones vigentes de CLAUDE.md.

## Global Constraints

- No inferir medidas observadas ni inventar evidencia de técnicos.
- No mezclar vectores de modelos, revisiones o modalidades diferentes.
- Respetar trabajos existentes y usar registros propios.
- Confirmación del usuario recibida para todo el alcance; no se requiere otro gate de diseño.
- Sin publicación o despliegue externo necesarios para la entrega local.

## Review Focus

- Acceso ajeno por IDs en path, body, artefactos derivados y jobs.
- Desconexión ASGI antes y después del body completo.
- Cancelación simultánea con finalización, FIFO y liberación única de plazas.
- Getter de localStorage bloqueado, cuota y errores de history.
- Cachés antiguas, snapshot ausente y metadatos semánticos incompatibles.

## Tareas y evidencia

- [x] Seguridad: tests ASGI de desconexión y Alice/Bob; migrar runs.owner_actor con backfill no ambiguo, comprobar documentos y derivados, cuerpos que referencian run/document y rutas de reconstrucción. Archivos main.py, servicios/repository.py, routers dependientes y tests de seguridad. 404 uniforme para recursos ajenos.
- [x] Jobs: executor acotado, cancelación queued/running, transición terminal atómica, checkpoints por llamada, posición FIFO. GET /api/v1/projects y /executions devuelve items y next_cursor filtrados por propietario. POST /jobs/{id}/cancel y GET job exponen cancel_requested, can_cancel y queue_position. Tests con Event y sin esperas arbitrarias.
- [x] Embeddings: sustituir proveedor runtime OpenAI por EmbeddingGemma 2 local fijado; separar espacio textual del mixto del explorador; clave de caché con revisión, modalidad, dimensiones y preprocesado. Actualizar configuración, metadata, consumidores y despliegue. Tests sin red y smoke real si snapshot disponible.
- [x] Frontend: capacidades reales del explorador, adaptador seguro de storage con memoria y URL, guard de revisión dirty, panel Proyectos separado de Biblioteca, cancelar y posición de cola. Tests Node y coordinación API con jobs.
- [x] Navegador: Playwright contra servidor aislado, recorrido carga/resultado/revisión/recuperación y storage bloqueado; CI Chromium con artefactos de fallo. No llamadas de proveedor externas.
- [x] Evaluación: esquema y scorer de sesiones técnicas con procedencia, omisiones, correcciones, coste/horas y tiempo; protocolo y plantilla; reproducir scores disponibles sin equipararlos a validación industrial.
- [x] Integración: revisión Astra de diffs; corregir hallazgos importantes; pytest, Node, E2E, compilación y paquete según impacto. Registrar resultados observados y límites.

Cada implementador escribe primero pruebas de comportamiento, observa el fallo cuando aplica, implementa y ejecuta su suite focal; registra comandos y resultado en su archivo. El coordinador ejecuta la verificación integrada después de cerrar los cambios.
