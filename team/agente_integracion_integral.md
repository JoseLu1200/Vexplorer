# Agente de integración integral — API y composición

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA de integración integral; no representa a una persona.
- Rol: integración backend del swarm GPT-6.1 Sol.
- Archivo creado y designado explícitamente: `team/agente_integracion_integral.md`, delegación renovada por el usuario el 2026-11-14.
- Última actualización: 2026-11-14, cierre de implementación local.

## Tarea de la sesión

- Objetivo concreto: conectar en la aplicación los adaptadores PDF/DWG, los módulos de mueble general e histórico real, publicar capacidades y conservar autenticación, actor, auditoría y flujos DXF/replay existentes.
- Referencia del plan: brechas T11–T13 y formatos P1 descritos en `initial-plan.md` y la transcripción.
- Estado: implementación local terminada; despliegue bloqueado hasta cierre de QA autónomo por coordinación.

## Alcance y reservas

- Archivos o carpetas que puedo editar: `backend/app/main.py`, nuevas pruebas de integración bajo `backend/tests/` y este registro. Coordinación transfirió además el cambio mínimo en `DemoRepository.finish_job` para enlazar un run parcial a un job fallido.
- Dependencias que solo leeré: adaptadores bajo `backend/app/ingesta/`, módulos nuevos de mueble general e histórico/economía, contratos, repositorio, operación y frontend.
- Archivos compartidos que requieren coordinación: símbolos y shapes de los módulos nuevos; sus responsables conservan la implementación de dominio.
- Solapes detectados y acuerdo para resolverlos: ningún otro agente actual editará `main.py`; este agente no editará módulos de dominio ni contratos compartidos.

## Hecho en el último bloque

- Levantada QA HTTP v5 aislada en `127.0.0.1:8769`, PID 48124 y data dir `.runtime/transcript-qa/v5-http`; no se tocó el proceso 8768.
- Verificados por SHA-256 e importados 19 registros publicados: 4 presupuestos Grotowska y 15 coeficientes horarios Nuriyev, sin rechazos.
- Ejecutado `tools.audit_autonomous` real sobre el DXF diagnóstico público `plank-001.dxf` con proposer `gpt-6.1-sol`, reviewer `gpt-6-astra`, 16.384 tokens y límites 5/2/300.
- Auditoría HTTP real aprobada 10/10: P1/R1, reviewer separado, estado `incomplete`, 3 ocurrencias provisionales y cero físicas; 4 escenarios condicionales produjeron costes 285,68/238,89/140,01/242,38 PLN y 3,5/2,5/3/2,5 h con provenance publicada y alta incertidumbre explícita.
- Smoke raster `visual-001.pdf`: página hija `needs_review`, sin DXF fabricado; PDF 57.735 B y PNG 57.360 B descartan cuota/render. El job duró 75,36 s, por debajo del timeout de 120 s, y falló antes de P1 (`general_live_provider_failed: RuntimeError`). La evidencia es consistente con tres tool args inválidos y `validation_repair_budget_exhausted`, no con transitorio; no se reintentó. La causa diagnóstica segura es que la frontera proposer no exporta error/trace tipado y main colapsa todos los `RuntimeError`; fix post-blind20: `GeneralLiveError` seguro equivalente al autónomo y trazas acotadas ligadas al job.
- Actualizada `.env.example` a configuración QA 16k y reviewer Astra; `OPENAI_VISION_ENABLED` queda documentado como flag del flujo legacy de mesa, no del contexto fuente general.

- Montados histórico real y mueble general antes del frontend estático, con bases `history.sqlite3` y `general_furniture.sqlite3` bajo el data dir por defecto.
- Publicadas capacidades compatibles con frontend sin romper flags live/replay/semantic existentes.
- Implementado upload DXF/DWG/PDF con cuota recursiva de originales y artefactos, manifests persistentes, descarga segura de original/normalizado, previews PDF y errores tipados.
- Implementada selección de página PDF como documento hijo inmutable, con escala opcional finita, actor/fecha/motivo, procedencia del padre y soporte raster visual sin inventar geometría.
- Integrado mueble general en jobs durables: live se ejecuta antes de crear el run para no dejar runs fantasma si falla; propuesta y eventos sanitizados se persisten antes de marcar el job exitoso.
- Añadido ciclo autónomo acotado proponente → crítico multimodal → reparación semántica opcional → crítico final. P1 queda inmutable, P2 se guarda por CAS cuando existe reparación y la revisión/derivación se liga a la revisión exacta.
- Separado el proveedor revisor mediante `VEXPLORER_GENERAL_REVIEW_MODEL`; defaults de QA: 16.384 tokens, 5 llamadas, 2 reparaciones de validación y 300 s totales, todos acotados y publicados en `/config`.
- Conectado `render_visual_evidence` para DXF, DWG normalizado y página PDF seleccionada; el contexto conserva vistas, contornos, referencias, crops, marcas y warnings hasta proposer y reviewer.
- Publicados eventos sanitizados de crítica, reparación y revisión automática con modelo/tokens, sin argumentos del proveedor ni cadena de pensamiento. El actor de revisión es siempre máquina.
- La ruta directa `/general/auto-review` existe pero responde durable-job-required; la reejecución operativa crea un job nuevo sobre el mismo documento y conserva la run anterior.
- P1 se checkpointa inmediatamente después del proponente y P2 inmediatamente tras la reparación, antes de C2. Si C2 falla, el job queda `failed` con `run_id`, P1/P2 y trazas seguras; no existe review exitosa falsa.
- Montado `/history/scenarios` con loader exacto P/R del servidor. Solo proyecta ocurrencias provisionales con cantidad hypothesis y checks correlacionados; no convierte hechos físicos ni usa latest/payload cliente.
- Cubierto el flujo positivo auto-review → BOM provisional → comparable real no sintético → escenario condicional con coste/horas/provenance.
- Integrado actor autenticado en uploads, revisiones generales e import histórico; evaluación permanece offline y no se monta en runtime.
- Migrados los fixtures económicos integrales al contrato de alcance explícito: registros labor-only declaran `included_scope`, `cost_scope` y `hours_scope`, y los targets exigen `required_cost_scope`/`required_hours_scope` coincidentes.
- Añadido límite ASGI real de 5 MiB para JSON sin confiar en `Content-Length`.
- Reproducido el DWG real comunicado por coordinación: salida absoluta del conversor frente a data dir relativo causaba `persistence_failed`; corregido y cubierto por regresión.

## Siguiente bloque

- Coordinación ejecuta revisión Astra, suite conjunta, navegador y despliegue; no quedan cambios propios previstos.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Mantener originales separados de artefactos normalizados y sumar ambos a cuota | Evitar pérdida de fuente y bypass de almacenamiento | Delegación y contrato de ingesta |
| 2026-11-14 | PDF queda `needs_review` con preview/ledger propio, nunca como DXF fabricado | No inventar geometría ni unidades | Interfaz publicada por ingesta |
| 2026-11-14 | Evaluación no se monta en runtime | La referencia privada no debe alcanzar API ni producto | Interfaz publicada por evaluación |

## Dependencias / avisos

- Necesito de: ingesta, mueble general y economía para firmas definitivas.
- Afecta a: frontend mediante `/api/v1/config`, upload y rutas nuevas.
- Aviso realizado: coordinación directa iniciada antes de editar producto.
- Persistencia/backup comunicados a operaciones: `vexplorer.sqlite3`, `general_furniture.sqlite3`, `history.sqlite3` y `documents/**`; excluir `.document-staging`.
- Configuración DWG comunicada: `VEXPLORER_DWG_CONVERTER`, `VEXPLORER_DWG2DXF_EXECUTABLE` y `VEXPLORER_ODA_EXECUTABLE` según proveedor.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| RED integración | `pytest backend/tests/test_integral_api_integration.py -q` antes de wiring | 4 fallos esperados: capabilities, source artifacts, PDF y actor ausentes | Confirmó huecos reales |
| Integración focal | `pytest` sobre integración, adversarial, general, histórico, auth, jobs, legacy y replay | 66 passed | Aviso conocido TestClient/httpx |
| PDF/DWG adversarial | `pytest backend/tests/test_multiformat_adversarial.py -q` | 2 passed | Fixtures locales, sin red |
| DWG real LibreDWG | TestClient con vanity DWG y `dwg2dxf.exe` local | HTTP 201 tras regresión RED/green de data dir relativo | Conversión requiere revisión técnica |
| Suite integral propia | `python -m pytest backend/tests/test_integral_api_integration.py -q` | 14 casos actuales | Incluye CAD/PDF raster visual, P1→P2, fallo C2 durable y escenario histórico positivo |
| Autónomo/router/visual/integración | `python -m pytest backend/tests/test_general_furniture_autonomous.py backend/tests/test_general_furniture_router.py backend/tests/test_general_furniture_visual_evidence.py backend/tests/test_integral_api_integration.py -q` | 28 passed | Verifica contrato dominio y composición HTTP |
| Integración ampliada focal | `python -m pytest backend/tests/test_integral_api_integration.py backend/tests/test_private_jobs.py backend/tests/test_general_furniture_autonomous.py backend/tests/test_general_furniture_router.py backend/tests/test_real_history.py -q` | 70 passed | Incluye jobs privados y economía provisional |
| QA HTTP v5 real | `python tools/audit_autonomous.py --base-url http://127.0.0.1:8769 --fixture ../plankassembly_adapter_trial_v1/plank-001.dxf --output .runtime/transcript-qa/v5-http/audit-plank-001.json --timeout 600` | PASS, 10 checks | Online, no oracle privado; un run con `--resume-report` añade el check 11 `resumed_existing_job`, no es un check funcional ausente |
| Suite Python completa fresca | `python -m pytest -q` | 578 passed, 99.83 s | Tras checkpoints autónomos y escenario económico provisional |
| Compilación | `.venv/Scripts/python.exe -m compileall -q backend` | exit 0 | No sustituye despliegue |
| Diff propio | `git diff --check -- backend/app/main.py backend/tests/test_integral_api_integration.py team/agente_integracion_integral.md` | sin salida | Trabajo compartido ajeno preservado |

## Bloqueos y cierre

- Bloqueos: ninguno dentro del alcance propio.
- Pendientes: suite completa fresca tras integración total y verificación HTTP/navegador/despliegue por coordinación.
- Reservas liberadas: `backend/app/main.py`, nueva prueba integral y este registro tras handoff.
- Entrega a otra persona: coordinación raíz recibe rutas, variables, resultados y límites.
