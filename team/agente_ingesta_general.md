# Agente de ingesta general — PDF y DWG

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA de ingesta general.
- Rol: adaptadores deterministas de entrada PDF y DWG.
- Archivo creado o designado explícitamente: delegación del swarm renovada por el usuario el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo vigente adicional, delegado expresamente el 2026-11-14: implementar el planner y los renderers CAD 2D del escenario constructivo general, con una lámina de conjunto cuando existan placements y una lámina acotada por tipo de pieza en SVG/DXF.
- Worktree: `.worktrees/cad-completion`, base `0e65713`; sin commits propios.
- Propiedad exclusiva de este bloque: nuevos módulos de planner/renderer bajo `backend/app/general_furniture/` y pruebas nuevas disjuntas correspondientes.
- Fuera de alcance: contratos Pydantic (backend general), validación constructiva (economía), wiring/API, frontend, PDF, 3D, histórico y despliegue.

- Objetivo concreto: implementar ingesta PDF vectorial/ráster con procedencia de escala y unidades desconocidas, y conversión DWG mediante ODA configurable con errores honestos.
- Referencia del plan: P1 de `initial-plan.md` y vacíos de `transcripcion-contexto-poc.md` relativos a formatos de entrada.
- Estado: terminado y verificado.

## Alcance y reservas

- Archivos o carpetas que puedo editar: nuevos módulos en `backend/app/ingesta/`, `backend/app/ingesta/__init__.py`, nuevas pruebas `backend/tests/test_ingesta_pdf.py` y `backend/tests/test_ingesta_dwg.py`, el subtask disjunto autorizado `backend/app/general_furniture/measurements.py` + `backend/tests/test_general_furniture_measurements.py`, el auditor integral `tools/audit_integral.py`, y este registro.
- Dependencias que solo leeré: `backend/app/ingesta/dxf_reader.py`, `backend/app/geometria/`, `backend/app/contratos/`, `backend/app/main.py`.
- Archivos compartidos que requieren coordinación: `backend/app/main.py`, contratos y wiring de API quedan en manos del agente backend/raíz.
- Solapes detectados y acuerdo para resolverlos: la reserva histórica general de ingesta de A se limita aquí; la delegación actual transfiere expresamente PDF/DWG a este agente y no se editará su lector DXF.

## Hecho en el último bloque

- Implementado `construction_planner.py`: una lámina por tipo de pieza rectangular/lineal explícito, vistas de cara/sección, cotas L/W/T, cantidad, estados observed/deduced/estimated, rangos y detalle local tipado; custom/unknown no inventa contorno.
- El conjunto 2D solo se emite con cobertura exacta y única de occurrence refs; placements ausentes, duplicados o incompletos conservan planos de pieza y omiten el montaje con warning.
- Implementado `construction_drawings.py`: SVG/DXF exactos en mm, artifacts snapshot-exactos, capas/colores/linetypes por autoridad, título/leyenda/restricciones visibles, provenance y cotas con terminadores.
- Detalle gráfico verificado: taladro circular estimado con diámetro/rango y leader ortogonal a zona reservada, sin clipping del texto.
- La proyección canónica de `derivations.py` enmascara dependencias rechazadas antes de invocar el planner; este módulo no duplica esa lógica.

- Implementado conversor DWG mediante ODA configurable, salida validada por el lector DXF real y errores tipados de disponibilidad, ejecución y salida.
- Añadido GNU LibreDWG `dwg2dxf` como proveedor preferido en modo `auto`; selección y ejecutables quedan explícitos por variables `VEXPLORER_*`, y ODA avisa que exige licencia autorizada.
- Implementada ingesta PDF con metadatos originales, preview por página, evidencia vectorial/textual, detección ráster y DXF por página.
- Las unidades PDF permanecen desconocidas salvo confirmación explícita; escalas enfrentadas a `DO NOT SCALE`/`NO ESCALAR` se avisan.
- Añadidos presupuestos por documento/página de paths, segmentos, puntos y píxeles, además del límite de bytes.
- Entregado ledger geométrico determinista para mueble genérico: spans y segmentos por contorno con procedencia y contexto de forma, sin convertirlos en dimensiones de componente ni cantidades.
- Añadida prueba HTTP adversarial multipágina: child vectorial escalado conserva página/unidad/provenance/aviso `DO NOT SCALE`; child ráster conserva preview y entra en revisión general sin DXF.
- Entregado `tools/audit_integral.py`: aceptación HTTP local/remota con Basic solo por entorno/input, jobs durables, propuesta/revisión general doble, snapshots/artefactos exactos, historial QA sintético, comparables/estimación, negativos de auth/CAS y DWG opcional.

## Siguiente bloque

- Ejecutar suite completa compartida y entregar interfaces/limitaciones finales.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | PDF conserva coordenadas en puntos y no las declara milímetros sin escala explícita | Evitar dimensiones fabricadas | Reglas de `AGENTS.md` y delegación actual |
| 2026-11-14 | DWG solo se procesa tras conversión real y salida DXF validada | No fingir soporte nativo | `CLAUDE.md` e `initial-plan.md` |

## Dependencias / avisos

- El planner CAD espera el contrato compacto congelado por backend general; no editará `backend/app/contratos/modelos.py`.
- Coordinados backend general, economía y frontend antes de editar producto en el worktree aislado.

- Necesito de: backend/raíz para conectar los adaptadores a upload/API.
- Afecta a: selección de parser por extensión y persistencia de metadatos de fuente.
- Aviso realizado: interfaz exacta se enviará al agente raíz antes de implementar.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| RED inicial | `python -m pytest backend/tests/test_ingesta_dwg.py backend/tests/test_ingesta_pdf.py -q` | 2 errores de import esperados | Módulos aún inexistentes |
| PDF límites/nota | `python -m pytest backend/tests/test_ingesta_pdf.py -q` | 2 fallos esperados | Segment budget y conflicto de escala aún ausentes |
| Adaptadores | `python -m pytest backend/tests/test_ingesta_pdf.py backend/tests/test_ingesta_dwg.py -q` | 11 passed | Conversores externos simulados; smoke LibreDWG real lo prepara operaciones |
| Regresión CAD | `python -m pytest backend/tests/test_ingesta_dwg.py backend/tests/test_ingesta_pdf.py backend/tests/test_ingesta_cad_geometry.py backend/tests/test_geometry.py backend/tests/test_pr1_cad_port.py -q` | 46 passed | No prueba wiring HTTP |
| Ledger geométrico general | `python -m pytest backend/tests/test_general_furniture_measurements.py -q` | 3 passed | Integrado por backend general |
| HTTP multipágina adversarial | `python -m pytest backend/tests/test_multiformat_adversarial.py -q` | 2 passed | No sustituye smoke de navegador |
| Suite completa | `python -m pytest -q` | 506 passed en 73.69 s | Conversor externo real se valida por operaciones |
| Lint propio | `python -m ruff check backend/app/ingesta backend/app/general_furniture/measurements.py backend/tests/test_ingesta_dwg.py backend/tests/test_ingesta_pdf.py backend/tests/test_general_furniture_measurements.py backend/tests/test_multiformat_adversarial.py` | pasa sin hallazgos | Alcance propio |
| Smoke LibreDWG real | `VEXPLORER_DWG_CONVERTER=libredwg` + `convert_dwg_to_dxf` sobre vanity DWG genuino | proveedor `libredwg_dwg2dxf`, unidad `m`, escala 1000, 130 entidades; hashes origen/DXF `ee2c7474...`/`f409ceb8...` | Un caso no demuestra fidelidad universal; el proveedor queda `requires_review` |
| Auditor integral local | `python tools/audit_integral.py --base-url http://127.0.0.1:18766 --output .runtime/integral-audit-local/report-v3.json` con credenciales por entorno | `passed`, 16 checks; auth/actor marcados SKIP por modo local | Producción debe convertir esos SKIP en PASS |
| Auditor integral + DWG | mismo comando contra puerto local aislado y `--dwg <vanity.dwg>` | `passed`, 16 checks; `optional_real_dwg` PASS con warnings LibreDWG honestos | Datos persistidos con prefijo `qa-integral-*` |
| Planos constructivos focal | `python -m pytest` sobre contrato, validación, review, planner, drawings y derivations | 42 passed | Sin modelo live; F01 lo ejecuta coordinación |
| Planner/renderer propio | `python -m pytest backend/tests/test_general_furniture_construction_{planner,drawings}.py -q` | 7 passed | Incluye gate de placements, detalle gráfico y artifacts SVG/DXF |
| Estática planos | `python -m ruff check ...`; `compileall`; `git diff --check` | correcto | Ruff disponible en Python global, no en venv |
| Inspección visual | PNG renderizado desde SVG propio | cotas/ticks/rangos/cantidad/restricción y callout completos, sin texto recortado | Artefacto `.runtime/cad-completion-drawings/pieza-side-panel-p2-r1.png` |

## Bloqueos y cierre

- Bloqueos: ninguno del código; la frontera externa se prueba con proceso simulado y DXF real validado.
- Pendientes: ejecutar `tools/audit_integral.py` contra el destino remoto autorizado tras despliegue/Astra; ampliar corpus si se exige fidelidad DWG universal.
- Reservas liberadas: `backend/app/ingesta/`, pruebas propias, `measurements.py` y prueba adversarial tras entrega.
- Reservas liberadas: no.
- Entrega a otra persona: pendiente.
