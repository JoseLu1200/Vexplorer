# Agente de consistencia constructiva — validación CAD

## Identidad y autorización

- Identidad: agente de IA de consistencia constructiva; no representa a una persona.
- Rol: validador determinista del escenario de construcción CAD.
- Archivo creado por delegación explícita del coordinador el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto: recalcular expresiones, intervalos, DAG, cierres y cantidades de escenarios de muebles inferidos desde vistas 2D pobres.
- Referencia: `docs/superpowers/specs/2026-11-14-cad-completion.md` y su plan homónimo.
- Estado: implementación focal terminada; esperando estabilización concurrente para suite conjunta.

## Alcance y reservas

- Propiedad exclusiva: `backend/app/general_furniture/construction_validation.py`, nueva prueba determinista disjunta y este registro.
- Solo lectura: contratos Pydantic, medidas, hipótesis de proyección, propuesta/materialización y revisión autónoma.
- No objetivo: economía, PDF, 3D, histórico, despliegue, renderer ni integración API.
- Solapes: backend general es único escritor contractual; coordinación directa iniciada antes de código.

## Plan

1. Consumir el contrato congelado sin modificarlo.
2. RED/GREEN de resolución de parámetros observados, estimados y deducidos.
3. RED/GREEN de referencias, intervalos, ciclos y profundidad máxima 8.
4. RED/GREEN de cierres y cantidades por ocurrencias, sin contar vistas.
5. Verificar focal, regresiones generales, lint, compilación y diff.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-14 | El validador no propone números ni componentes | La interpretación pertenece al modelo; el servidor recalcula y contradice | Especificación y acuerdo con backend general |
| 2026-11-14 | Una deducción dependiente de estimación conserva estado estimado | Cerrar una ecuación no crea observación | Especificación vigente |
| 2026-11-14 | Los intervalos usan formas afines sobre variables base compartidas | Evita falsos conflictos al reutilizar un mismo espesor | Invariante explícita de root |
| 2026-11-14 | V1 valida cantidad y base sin vistas, pero no fabrica ocurrencias | Review/autonomous crea IDs provisionales tras sus checks | Freeze de backend general |

## Dependencias / avisos

- Necesito de: backend general, nombres contractuales finales y ejemplo compartido.
- Afecta a: materialización y crítica automática, que consumirán el informe.
- Aviso realizado: mensaje directo a `/root/general_backend` antes del primer test.
- Cambio de `contratos/`: no aplica; este agente no los editará.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| RED módulo ausente | focal propio | `ModuleNotFoundError` esperado | antes de producción |
| Correlación/cierre | focal propio | `600=18+564+18` pasa; `604/600` falla | correlación exacta |
| `scale_rational` RED/GREEN | prueba focal y archivo completo | fallo esperado y después pasa | factor racional exacto |
| Faltante RED/GREEN | prueba focal y archivo completo | fallo esperado y después pasa | incomplete, no conflicto falso |
| Profundidad RED/GREEN | prueba focal y archivo completo | fallo esperado y después pasa | ocho niveles; noveno rechazado |
| Focal final propio | `python -m pytest backend/tests/test_general_furniture_construction_validation.py -q` | 13 passed | incluye bounds y coherencia de círculo |
| Ruff/compile/diff | comandos sobre archivos propios | correcto | ninguno |
| Revisión Astra focal | lectura independiente + focal | 13 passed; sin blocker residual | alcance del validador |
| Regresión general | `python -m pytest backend/tests -k general_furniture -q` | colección bloqueada | `_review_target_refs` concurrente ausente |
| Propuesta+contrato+validador | tres archivos focales | 21 passed, 1 fallo concurrente | fixture contractual usa `contour:side` fuera de autoridad |

## Bloqueos y cierre

- Bloqueos: suite conjunta temporalmente roja por edición concurrente de `autonomous.py`, fuera de esta reserva.
- Pendientes: suite conjunta tras GREEN de integration/Astra.
- Reservas liberadas: ninguna.
- Entrega: `validate_construction_scenario(proposal, draft) -> GeneralConstructionValidation`; root integrará archivos explícitos y este agente no creará commit propio.

## Incremento de producción: reintentos durables

- Delegación posterior: endpoint `POST /api/v1/jobs/{job_id}/retry`, persistencia del enlace y cuota diaria del modo live público.
- Archivos: `backend/app/servicios/repository.py`, bloque jobs/config de `backend/app/main.py` y `backend/tests/test_private_jobs.py`.
- Garantías: solicitud original reutilizada; un sucesor por origen y actor; ajenos ocultos como 404; solo `failed|interrupted` con `retryable=true`; cuota UTC global/cliente atómica y durable, sin cobrar replay.
- Verificación: focal jobs `10 passed`; jobs+auth+integral `39 passed`; compileall y diff-check correctos.
- Revisión Astra: aprobada sin blocker funcional; se añadió `Retry-After` y `X-RateLimit-Reset` UTC a su recomendación.
