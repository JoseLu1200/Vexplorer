# Agente de jobs, cancelación y recientes

## Identidad y autorización

- Nombre declarado: agente de IA `jobs`; no representa a una persona.
- Rol: trabajos durables, concurrencia acotada, cancelación cooperativa y API de proyectos/ejecuciones recientes.
- Archivo designado por coordinación y autorizado explícitamente por el usuario el 2026-11-14.
- Historia real: el primer bloque de implementación se inició al interpretar una asignación de propiedad del coordinador como autorización de edición, antes de recibir la confirmación explícita posterior del usuario. No se oculta ni se reescribe ese orden; la autorización explícita ya fue confirmada antes de continuar este bloque.

## Tarea de la sesión

- Sustituir el worker serial por concurrencia local acotada.
- Permitir cancelación durable e idempotente de trabajos queued/running sin afirmar que una llamada externa ya iniciada puede abortarse.
- Exponer posición de cola y vistas recientes de proyectos/ejecuciones aisladas por actor.
- Estado: jobs/cancelación y recientes implementados; ownership de seguridad integrado; verificación conjunta en curso.

## Alcance y reservas

- Propiedad principal: `backend/app/operacion/jobs.py`, persistencia del ciclo de vida de jobs en `backend/app/servicios/repository.py`, pruebas `backend/tests/test_job_executor.py` y `backend/tests/test_job_lifecycle.py`.
- Integración coordinada: secciones acotadas de jobs/config/rutas en `backend/app/main.py`; callbacks cooperativos en runners de agente.
- Configuración: `.env.example`, `compose.yaml`, `deploy/*production.env.example`, `docs/PRODUCCION.md`.
- Seguridad conserva: migración `runs.owner_actor`, guards de documentos/runs y validación central de recursos.
- Sin commits ni despliegue.

## Hecho

- `BoundedJobExecutor` admite hasta cuatro workers, dos por defecto, manteniendo admisión total acotada.
- Registro por job de Futures: cancelación de queued libera exactamente una reserva; running usa token cooperativo.
- Persistencia `cancel_requested_at`, terminal `cancelled` y transición atómica donde una cancelación confirmada gana frente a success/failure concurrente.
- Posición FIFO durable mediante orden `rowid`, incluida prueba con timestamps empatados e IDs inversos.
- Ruta genérica actor-scoped `POST /api/v1/jobs/{job_id}/cancel` y compatibilidad actor-scoped para cancelación de montaje.
- Callbacks antes y después de cada llamada al proveedor en legacy, piezas, mesa, proponente general, crítico autónomo y montaje.
- Campos de polling: `cancel_requested`, `queue_position`, `can_cancel`.
- `VEXPLORER_JOB_MAX_WORKERS=2` documentado en ejemplos de entorno y producción.
- `/api/v1/projects` y `/api/v1/executions` publican el contrato paginado congelado, con cursores opacos, límites 1–100, aislamiento por actor y desactivación en producción pública sin autenticación.
- Los cursores validan esquema y tipos exactos: secuencia entera positiva no booleana; proyecto con fecha ISO zonificada e ID de documento canónico. Base64 válido con tipos falsos también devuelve 422.
- `link_job_run` impide enlazar un job y un run de propietarios distintos; recientes vuelve a verificar ownership de documento y run antes de publicar cada elemento.
- La cancelación autónoma ya no registra un fallo genérico engañoso y la ruta de montaje no duplica el evento de auditoría al repetir una cancelación.

## Pruebas y revisión

| Comprobación | Resultado |
|---|---|
| Ciclo TDD inicial de executor/lifecycle | fallos esperados observados antes de cada implementación principal |
| Regresión focal previa | 76 passed |
| Agente/mesa/general tras callbacks | 89 passed |
| Suite completa anterior al último callback | 1430 passed, 2 warnings |
| Revisión Astra final del alcance jobs | APPROVE; 131 pruebas relevantes, 131 passed |
| Regresión conjunta jobs + seguridad + recientes | 147 passed |
| Revisión Astra jobs + recientes tras cursores estrictos | APPROVE; sin P1/P2 pendientes |
| `py_compile` y `git diff --check` | aprobados |
| Ruff | no disponible en `.venv` (`No module named ruff`) |

## Riesgos y pendientes

- Una llamada HTTP al proveedor ya iniciada no se mata; la cancelación se observa inmediatamente al retornar y antes de otra llamada o publicación controlada.
- Artefactos de una fase ya completada pueden permanecer; `cancelled` no significa rollback transaccional entre bases distintas.
- Observabilidad entre bases distintas sigue siendo eventual: una fase ya completada puede conservar artefactos aunque el job termine `cancelled`; no se presenta como rollback.

