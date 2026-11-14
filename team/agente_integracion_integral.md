# Agente de integración integral — API y composición

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA de integración integral; no representa a una persona.
- Rol: integración backend del swarm GPT-6.1 Sol.
- Archivo creado y designado explícitamente: `team/agente_integracion_integral.md`, delegación renovada por el usuario el 2026-11-14.
- Última actualización: 2026-11-14, fase CAD completion en worktree aislado.

## Tarea de la sesión

- Objetivo vigente: integrar el resultado constructivo provisional de vistas CAD 2D, con valores `estimated` aceptados dentro de BOM y planos por pieza, snapshots exactos P/R, eventos y artefactos descargables; conservar DrawingExtraction como observación inmutable.
- Worktree/base: `.worktrees/cad-completion`, `0e65713`. No hay deploy ni uso de 8771.
- Propiedad actual: `backend/app/main.py`, `backend/app/general_furniture/router.py`, `backend/app/general_furniture/repository.py`, tests de router/repositorio/integración y este registro. Contratos/inferencia/derivaciones pertenecen a general_backend; planner/renderers a ingesta; validación determinista a economy.
- Decisión de persistencia congelada: sin tabla nueva; proposal/draft/review/derived JSON permanecen inmutables por CAS P/R. `GeneralDerivedPackage.construction` y artefactos por pieza quedan ligados a P/R exactos; `basis_revision` incluye run/P/R/scenario.
- Avance temprano: GET general acepta query P/R exacta sin romper latest; repositorio rechaza derived cuya run/P/R no coincide con review; runner QA local preparado bajo `.runtime/cad-completion-http` para F01 y puerto 8773, sin secretos ni oráculo.

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
- Smoke raster `visual-001.pdf`: página hija `needs_review`, sin DXF fabricado; PDF 57.735 B y PNG 57.360 B descartan cuota/render. Una única reproducción instrumentada preservó solo argumentos de tools y códigos seguros (`.runtime/transcript-qa/v5-http/raster-instrumented.json`, SHA-256 `dceaa7aeaeab76b9878568d3df5ec754b41e17c9e468b1c54c2f2b2e47078076`): C1 produjo una propuesta Pydantic-válida con dimensiones unknown, pero inventó `source_view_ids=["pdf-page-0001"]` sobre un ledger raster sin vistas y el materializador la rechazó con `proposal_reference_outside_ledger`; además usó el `source_document_refs` anunciado, que no pertenece al conjunto `allowed_document_refs` actual. C2 inspeccionó el ledger vacío correctamente y C3 acabó con `provider_response_incomplete`. No se reintentó. El proveedor descarta hoy `incomplete_details`, status/código HTTP y request id, por lo que ese submotivo no es recuperable. Fix post-blind20: unificar refs de artefacto y documento anunciadas, prohibir refs de ledger visuales inexistentes, `GeneralLiveError` con traza/counters previos y observabilidad segura de transporte/incomplete ligada al job, sin retries automáticos.
- Fix raster validado en el worktree aislado `conditional-hours`: `ProviderError` conserva solo status/código/request/response/incomplete reason acotados y `main` persiste el código, traza y contadores seguros de `GeneralLiveError` sin crear run fantasma. Suite completa 616/616. Smoke HTTP real en 8772 (servidor detenido al terminar) produjo job `job-b2a47a4baec9483893597f2311649071`, run `run-68ce10ee40624492813022bb24c6d332`, P2/R1 con `semantic_repairs=1` (P1→crítica conflict→P2→C2 incomplete), cinco componentes con largo/ancho/espesor `unknown`, seis ocurrencias provisionales y derived 200. Report SHA-256 `57059ac561723268cb97c94806e1e2f30ffc3d15f8d98e21bd6aae8f10578216`; 8771 permaneció intacto.
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
