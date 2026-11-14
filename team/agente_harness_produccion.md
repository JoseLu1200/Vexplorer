# Agente harness producción — refuerzo Task 1

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA de harness de producción; no representa a una persona.
- Rol: apoyo de backend para Task 1.
- Archivo creado y alcance designado explícitamente por la delegación del coordinador del 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto: endurecer deadlines totales de los tres runners y conservar telemetría segura y acotada del proveedor en acciones/traza.
- Referencia del plan: Task 1 de `docs/superpowers/plans/2026-11-14-private-production.md` y diseño privado asociado.
- Estado: terminado; verificación focalizada verde e integración de persistencia confirmada.

## Alcance y reservas

- Archivos que puedo editar: `backend/app/agente/runner.py`, `backend/app/agente/provider.py`, `backend/app/agente/config.py`, nuevo `backend/tests/test_agent_runtime.py`, este archivo y `.runtime/production/runner-report.md`.
- Dependencias que solo leeré: consumidores backend, contratos, herramientas, tests existentes y documentación del proyecto.
- Coordinación: publicaré al agente backend la forma de telemetría segura para que persista la traza sin solapar su propiedad.
- Solapes detectados: el backend conserva API/modelos/persistencia; este apoyo no editará esos archivos. La reserva puntual del coordinador prevalece para los tres módulos del harness.

## Hecho en el último bloque

- Reproducido en RED que los tres runners aceptaban respuestas terminales recibidas después del deadline y que una herramienta local lenta terminaba como agotamiento de llamadas, no timeout.
- Centralizado el cálculo de deadline y revalidado antes/después de proveedor y herramienta; una respuesta terminal tardía ya no se acepta.
- Añadida telemetría opcional y retrocompatible a `ProviderResponse`/`AgentAction`: IDs, modelo, duración y contadores de tokens sanitizados y acotados.
- El proveedor HTTP aplica el presupuesto restante como timeout nativo y transforma fallos HTTP/respuestas inválidas en códigos estables sin cuerpo remoto ni credenciales.
- Cerrado el hueco de memoria del transporte: lectura streaming en chunks de 64 KiB, máximo real de 4 MiB antes de JSON, sin confiar en `Content-Length`, y deadline comprobado durante la lectura.
- Interfaz final publicada a `/root/production_backend` para persistencia explícita de siete campos seguros; uso/duración son por respuesta y deben deduplicarse por `provider_response_id`, no sumarse por herramienta.
- `/root/production_backend` confirmó la integración explícita de los siete campos en `main.py`, sin raw ni agregación incorrecta.
- Confirmado el diff propio real: `runner.py`, `provider.py`, test runtime nuevo, este registro e informe ignorado; `config.py` quedó sin cambios.

## Siguiente bloque

- Ninguno dentro del alcance propio; el coordinador ejecutará la suite global una vez estabilizados los cambios paralelos.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo |
|---|---|---|---|
| 2026-11-14 | No prometer interrupción dura de proveedores Python arbitrarios | Un deadline cooperativo no puede matar cómputo CPU bloqueante | Delegación del coordinador |

## Dependencias / avisos

- Necesito de: backend para persistir la información segura ya expuesta por el outcome.
- Afecta a: trazas y persistencia de ejecuciones del agente.
- Aviso realizado: nombres finales comunicados a `/root/production_backend` el 2026-11-14; confirmó que persistirá solo campos explícitos.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Regresiones runtime | `python -m pytest backend/tests/test_agent_runtime.py -q` | 9 passed | Delay cooperativo; no prueba interrupción dura de CPU arbitraria |
| Harness/API focalizado | `python -m pytest backend/tests/test_backend_agent.py backend/tests/test_backend_table_agent.py backend/tests/test_backend_parts_api.py backend/tests/test_backend_table_api.py backend/tests/test_agent_runtime.py -q` | 37 passed, 1 warning deprecación externo | Sin llamadas pagadas |
| Suite Python completa | `python -m pytest -q` | 344 passed, 7 failed | 6 RED concurrentes de costes; 1 reproducibilidad de preparador fuera de alcance |
| Estática | `python -m compileall -q backend/app/agente`; `git diff --check -- ...` | pasa sin salida | `ruff` no está instalado en el venv |

## Bloqueos y cierre

- Bloqueos: ninguno del alcance propio.
- Pendientes: cierre global por coordinación.
- Reservas liberadas: `backend/app/agente/{runner,provider,config}.py` y `backend/tests/test_agent_runtime.py` tras esta entrega.
- Reservas liberadas: ninguna.
- Entrega a otra persona: pendiente.
