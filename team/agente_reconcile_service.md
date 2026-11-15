# Agente reconciliación de servicio R13

## Identidad y autorización

- Nombre declarado por coordinación: `/root/reconcile_service`, agente IA del swarm Sol + Astra autorizado por el usuario.
- Rol: portar de forma aditiva el delta R13 del servicio sobre `a467280`, preservando main y el diseño de `8022ac6`/`a467280`.
- Última actualización: 2026-11-15, implementación y verificación focal completadas.

## Alcance y reservas

- Archivos editables: `backend/app/main.py`, `backend/tests/test_integral_api_integration.py`, `backend/tests/test_general_test_timeout_injection.py` y este registro.
- Worktree de integración: `.worktrees/cutlist-design-integration`; el worktree antiguo `.worktrees/similarity-public` es solo lectura.
- Se preservan la recuperación durable y checkpoints de `bc3a17f`, EmbeddingGemma 2, montaje, cancelación, precedentes y el diseño incorporado.
- Sin cambios de contratos, claves/API, datos, frontend, `diseno/` ni commits.

## Tarea

- Portar exclusivamente el perfil local de prueba inyectado 1800/900 y las expectativas seguras de error/traza que aún falten.
- Mantener los timeouts productivos actuales y exigir ambos proveedores inyectados para ampliar el presupuesto.
- Coordinar `AutoReviewLimits.allow_extended_test_timeout` con `/root/cutlist_recovery_fix`.

## Estado y evidencia

- Inspección completada: `main` actual ya supera al worktree antiguo en recuperación durable, cancelación, montaje, detalles seguros del proveedor y persistencia de run; no se reemplazarán esos bloques.
- Baseline global del coordinador fue interrumpido y no se usa como evidencia; las pruebas focales se registrarán aquí.
- TDD RED observado: el test nuevo rechazó `allow_extended_test_timeout` inexistente; la prueba de traza durable detectó que faltaba el evento terminal seguro del proveedor.
- `backend/tests/test_general_test_timeout_injection.py`: `13 passed, 1 warning`.
- `backend/tests/test_integral_api_integration.py`: `18 passed, 1 warning`.
- `backend/tests/test_job_recovery.py`: `10 passed, 1 warning`; confirma defaults productivos `600/300` y recuperación vigente.
- Config/error focal: `2 passed, 1 warning`; traza durable aislada: `1 passed, 1 warning`.
- `py_compile` y `git diff --check` sobre el alcance: exit 0.
- `ruff` no estaba instalado en la venv (`No module named ruff`); no se presenta como ejecutado.
- Revisión focal solicitada al Astra existente mediante mensaje con archivos y evidencia.

## Cierre

- Sin commits. El coordinador conserva la suite global y la integración final.
- Reservas de los tres archivos entregables liberables tras la revisión.

