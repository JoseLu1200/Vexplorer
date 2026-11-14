# Agente assembly runtime — ejecución y persistencia

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA `assembly_runtime`; no representa a una persona.
- Rol: runtime acotado, persistencia y API del montaje general.
- Archivo creado explícitamente por encargo de `/root` con autorización del usuario, 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: implementar el bucle nativo de herramientas para montaje, persistir cada intento ligado a revisiones y añadir fase/reintento durable sin gasto en GET.
- Referencia: `docs/superpowers/specs/2026-11-14-general-assembly-design.md`.
- Estado: implementación terminada; verificación conjunta verde y ensayo live coordinado por raíz.

## Alcance y reservas

- Archivos propios: nuevo `backend/app/general_furniture/assembly_live.py`, `backend/tests/test_general_furniture_assembly_live.py`, pruebas nuevas de persistencia/API y este registro.
- Archivos compartidos con edición mínima coordinada: `backend/app/general_furniture/repository.py`, `backend/app/general_furniture/router.py`, `backend/app/main.py`.
- Solo lectura: `backend/app/contratos/modelos.py` (escritor exclusivo `assembly_core`), `backend/app/general_furniture/assembly.py`, frontend y referencias privadas.
- Solapes: `main.py` y módulos generales contienen cambios concurrentes; se preservan y solo se añaden hunks acotados. Interfaz contractual coordinada directamente con `assembly_core`.

## Hecho en el último bloque

- Runtime nativo estricto con inspect/evaluate/final, reparación, límites 5/180s/100/512, payload acotado, imágenes públicas, deadline y cancelación cooperativa.
- Persistencia CAS por revisiones y assembly revision; intentos fallidos separados de BOM, escena solo del intento actual aceptado y alternativas compatibles visibles.
- GET exacto sin gasto, fase durable posterior a auto-review, POST retry durable y cancelación persistida del retry.
- Diagnóstico seguro conserva códigos, rutas de validación, recuentos de llamadas y metadatos operativos del proveedor sin razonamiento interno.

## Siguiente bloque

- Entregar interfaz y evidencia a raíz; no reiniciar ni desplegar desde este agente.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-14 | No crear worktree ni commits | El usuario/root exige preservar y coordinar cambios concurrentes en el árbol compartido | Encargo `/root/assembly_runtime` |
| 2026-11-14 | Una escena solo se superpone si candidato, propuesta y revisión coinciden y el reporte es válido | Evitar servir montaje obsoleto o rechazado | Diseño aprobado |

## Dependencias / avisos

- Necesito de: `assembly_core` para contratos Pydantic y validador determinista.
- Afecta a: integración durable de `main.py` y consumo frontend de la fase/escena.
- Aviso realizado: mensaje directo a `assembly_core` antes de implementar.
- Cambio de `contratos/`: no lo realiza este agente; autorizado y delegado al escritor exclusivo.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| Runtime/core/repositorio/router/API | `.venv\\Scripts\\python.exe -m pytest backend/tests/test_general_furniture_assembly.py backend/tests/test_general_furniture_assembly_live.py backend/tests/test_general_furniture_repository.py backend/tests/test_general_furniture_router.py backend/tests/test_integral_api_integration.py::test_general_assembly_phase_persists_failure_and_retry_uses_durable_job -q` | 38 passed | Sin red; proveedor simulado |
| General furniture | `.venv\\Scripts\\python.exe -m pytest backend/tests -k general_furniture -q` | 124 passed | Antes de los últimos deltas contractuales; focal conjunto posterior verde |
| Ruff propio | `python -m ruff check` sobre runtime/repositorio/router y pruebas propias | pasa | `main.py` conserva hallazgos preexistentes ajenos |
| Suite global | `.venv\\Scripts\\python.exe -m pytest -q` | 786 passed, 2 warnings deprecación | Ejecutada antes del último guard atómico de cancelación; focal posterior 40 passed |
| Focal final post-cancelación/traza | assembly/core/runtime/repository/router/API | 45 passed | Incluye rechazo atómico, terminal diagnóstico con placements sin escena y códigos preflight exactos |

## Bloqueos y cierre

- Bloqueos: ninguno de implementación propia.
- Pendientes: evidencia live/evaluación y reinicio pertenecen a raíz/QA; no se afirma éxito geométrico del caso complejo hasta medirlo.
- Reservas liberadas: archivos propios listos para integración, 2026-11-14.
- Entrega: modelos/validador de `assembly_core`; estado wrapper y rutas comunicadas a viewer/live QA/root.
