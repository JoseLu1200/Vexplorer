# Astra — revisión independiente de hallazgos

## Identidad y autorización

- Nombre declarado por el usuario: Astra
- Rol: revisor independiente, solo lectura de implementación
- Archivo creado o designado explícitamente: `team/agente_hallazgos_review.md`, autorizado el 2026-11-14
- Última actualización: 2026-11-14

## Tarea de la sesión

- Objetivo concreto: revisar seis correcciones y mejoras asociadas, detectar defectos de seguridad, concurrencia, migración y aceptación antes del cierre.
- Referencia del plan: revisión transversal extraordinaria solicitada por el usuario.
- Estado: revisión técnica completada; pendiente solo incorporar el recibo de suite global de coordinación

## Alcance y reservas

- Archivos o carpetas que puedo editar: solo este registro de hallazgos.
- Dependencias que solo leeré: todo el repositorio y los diffs compartidos.
- Archivos compartidos que requieren coordinación: ninguno; no editaré implementación.
- Solapes detectados y acuerdo para resolverlos: ninguno.

## Hecho en el último bloque

- Convertidos los seis problemas en criterios de aceptación concretos.
- Auditado y aprobado el bloque de jobs: cancelación cooperativa, transición terminal atómica, FIFO global persistido, concurrencia configurable, recientes por actor y cursores tipados.
- Delimitadas superficies IDOR indirectas y la frontera de catálogo publicado compartido.
- Aprobado el bloque de seguridad: desconexión inmediata y a mitad de cuerpo, ownership de documentos/runs/IDs en body/reconstrucción y migración conservadora.
- Aprobada la evaluación técnica: agrega evidencia declarada sin fingir causalidad ni observaciones empíricas.
- Corregidos y revalidados los bloqueos de embeddings: regeneración legacy, identidad exacta, dependencias/despliegue, serialización de inferencia, embeddings ausentes y prohibición de umbrales OpenAI no calibrados en EG2.
- Corregidos y revalidados los bloqueos de frontend/CI: dependencia y script Playwright, guardas de navegación, refresco de recientes al completar y almacenamiento bloqueado.
- Endurecido el fallo cerrado de manifests corruptos tras una observación tardía de revisión.

## Siguiente bloque

- Incorporar el recibo final de la suite global y entregar veredicto agregado a coordinación.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Biblioteca publicada puede ser compartida; fuentes no publicadas permanecen privadas. | Es la frontera explícita comunicada por coordinación. | Mensaje del coordinador `/root`. |
| 2026-11-14 | EG2 texto e EG2 mixto son espacios distintos. | Evita mezclar vectores de modalidad y preprocesado incompatibles. | Decisión documental y mensaje del coordinador. |

## Dependencias / avisos

- Necesito de: diffs finales de cada implementador.
- Afecta a: coordinación y cierre de aceptación.
- Aviso realizado: criterios iniciales, mapa IDOR y revisión de jobs enviados a `/root`; detalles de jobs enviados a `/root/jobs`.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Jobs y agentes relevantes | `python -m pytest -q` sobre 10 módulos focales | 131 pasan | No sustituye suite total final. |
| Seguridad, jobs y evaluación | `python -m pytest backend/tests/test_security_ownership.py backend/tests/test_job_lifecycle.py backend/tests/test_job_executor.py tests/test_technician_study_evaluation.py -q` | 37 pasan en 26,07 s | Selección focal. |
| Sintaxis Python y whitespace | `python -m compileall -q backend evaluation tools tests/test_technician_study_evaluation.py` y `git diff --check` | Correcto; solo avisos LF/CRLF | El árbol seguía en mutación. |
| Frontend unitario durante integración | `npm test --prefix frontend` | 1 fallo por expectativa obsoleta de orden de arranque | Comunicado a frontend; requiere repetición al estabilizar. |
| Frontend unitario final | `npm test --prefix frontend` | 273 pasan | Ejecución final tras actualizar la expectativa. |
| Navegador final | `npm run test:browser --prefix frontend` | 6 pasan en 12,7 s | Un primer intento colisionó con otra ejecución simultánea en el puerto local fijo; la repetición limpia pasó. |
| Embeddings final focal | `python -m pytest` sobre embeddings, histórico, regeneración, biblioteca, similitud técnica, clustering y abstención | 107 pasan en 25,49 s | No ejecuta pesos reales; el smoke offline real fue aportado por el implementador/coordinador. |
| Manifest ownership focal | `python -m pytest backend/tests/test_security_ownership.py -q` | 16 pasan en 9,75 s | Verifica también fallo cerrado de manifest corrupto. |

## Bloqueos y cierre

- Bloqueos: ninguno en la revisión del diff actual.
- Pendientes: recibo de suite global de coordinación y limitación ya declarada de no poder construir Docker sin daemon.
- Reservas liberadas: no aplica mientras siga la revisión.
- Entrega a otra persona: hallazgos priorizados a coordinación; sin cambios de implementación.
