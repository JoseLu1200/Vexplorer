# Prueba de la app sobre otros datasets

Fecha: 2026-11-14. Esta es una prueba de comportamiento de una instantánea local de la app, no una evaluación de exactitud de despiece ni de precios.

## Alcance y procedencia

Se hicieron dos capturas acotadas del estado observable de `feat/transcript-completion`, sin sobrescribir la primera. La referencia final es `D:/Vexplorer-semantic-lab/cross-dataset/app-snapshot-v2`; v1 queda como contraste temporal. En ambas:

- Git HEAD: `42095101ac93c9c39d62271a62333ed924f8e51c`.
- Rama: `feat/transcript-completion`.
- El repositorio fuente tenía cambios tracked y untracked; no se modificó ni se hizo commit.
- La instantánea contiene 65 archivos Python/configuración de `backend/app`, `backend/__init__.py` y `pyproject.toml`. Excluye `.git`, `.env`, frontend, tests y datos runtime.
- `snapshot_provenance.json` conserva el HEAD, rama, `git status --short` y el SHA-256 de cada archivo incluido. v2 coincidió con la fuente y la fuente no cambió durante la captura.
- La verificación final de v2 encontró 68/68 archivos idénticos antes/después de la corrida, sin cambios.

Entre v1 y v2 cambiaron exactamente cuatro archivos, aunque el HEAD siguió siendo el mismo: `backend/app/api/history.py`, `backend/app/historico/models.py`, `backend/app/historico/real_service.py` y `backend/app/contratos/modelos.py`. No se hicieron más recapturas: v2 es la referencia final y no se extrapola a cambios posteriores sin commit.

## Ejecución hermética

El runner reproducible es `python -m tools.semantic_lab.probe_app run`. Lanzó un subproceso con el Python del `.venv` de la app, importó primero desde la instantánea y usó `FastAPI TestClient` en proceso. `VEXPLORER_ENV=local`; las bases SQLite, originales subidos y artefactos finales se escribieron solo bajo `D:/Vexplorer-semantic-lab/cross-dataset/app-v2/runtime-data`. No se levantó el servicio activo ni se tocó producción.

El recorrido final fue `geometry_only` con proveedor deshabilitado por configuración. No hubo instrumentación de actividad de red ni facturación, por lo que no se afirma una auditoría de cero llamadas o cero pago; coste `null` significa no medido. `execution_assessment.json` corrige expresamente esta lectura, ya que `results.json` conserva dos contadores declarativos del runner histórico que no son mediciones. Un primer intento v1 no autoritativo reveló que el `app` global escribe al importar si no se fija `VEXPLORER_DATA_DIR`; esos artefactos quedaron aislados y no intervienen en v2.

Disponibilidad live: configuración incompleta, falta `OPENAI_MODEL`. `AgentSettings.available` exige la configuración completa; no se inventó modelo y no se ejecutaron los tres casos live. Esta corrida no prueba la capacidad LLM ni visión de la app.

## Muestra determinista

Se probaron 53 archivos públicos, sin `_private`, sidecars de respuesta ni oráculos de piezas:

| Grupo | N | Selección |
|---|---:|---|
| Mecánico | 14 | `engineering_evaluation_pilot_v3/agent_inputs/cad-001..014.dxf` |
| PlankAssembly test | 10 | `plankassembly_adapter_test_v1/plank-001..010.dxf` |
| PlankAssembly trial | 6 | `plankassembly_adapter_trial_v1/plank-001..006.dxf` |
| CADBlock fuera del core | 20 | Round-robin ordenado por categoría/nombre; excluye `beds`, `buffets`, `simple-tables`, `sofas` |
| PDF mecánico | 3 | `visual-001..003.pdf` de `agent_inputs` |

Los 20 CADBlock cubren 16 categorías: `bathroom-set`, `bathtubs`, `dining-sets`, `doors-elevation`, `doors-plan`, `kitchen-appliances`, `kitchen-sinks`, `living-room`, `palm-trees`, `ranges`, `restaurant-layouts`, `sanitary-ware`, `toilets`, `trees-3d`, `trees-elevation` y `trees-plan`. El listado y SHA-256 exactos están en `request.json`/`results.json` externos.

## Resultados observados

### Subida e ingesta

- 53/53 `POST /api/v1/documents` devolvieron 201.
- Los 50 DXF quedaron con ingesta `ready`, DXF normalizado y capacidad `geometry_analysis=true`.
- Los 3 PDF quedaron `needs_review`, unidad desconocida, página raster y `geometry_analysis=false`; conservaron preview PNG para revisión de página.

Esto acredita aceptación/persistencia aislada y disponibilidad declarada de ingesta. No acredita semántica ni despiece.

### Extracción geométrica general

Cada documento se ejecutó con `mode=geometry_only`, `input_kind=general_furniture`, `proposal_mode=none`, y se consultó su `drawing` persistido.

| Grupo | Estado extractor | Unidad | Entidades | Vistas | Contornos | Cotas | Observaciones |
|---|---|---|---:|---:|---:|---:|---:|
| Mecánico, 14 | 14 `needs_review` | 3 `mm`, 11 `source` | 2.867 | 30 | 50 | 316 | 30 |
| Plank test, 10 | 10 `ready` | 10 `mm` | 1.152 | 10 | 251 | 0 | 10 |
| Plank trial, 6 | 6 `ready` | 6 `mm` | 648 | 6 | 131 | 0 | 6 |
| CADBlock, 20 | 15 `ready`, 5 `needs_review` | 20 `mm` | 6.825 | 20 | 182 | 108 | 20 |
| PDF, 3 | 3 `needs_review` | 3 `source` | 0 | 0 | 0 | 0 | 0 |

Los conteos son objetos producidos por el extractor, no aciertos contrastados. En particular, los 16 Plank tienen contornos y escala métrica pero ninguna cota; no se consultó su referencia privada para completar piezas.

### Propuestas, despiece y abstención

- Los 53 runs generales se crearon con estado/result `needs_review`, cero `pieces` y cero escenarios.
- `GET /api/v1/runs/{id}/general` devolvió 404 `general_proposal_not_found` en los 53. Es el comportamiento contractual: `general_furniture + geometry_only` no genera propuesta; `model_generated` exige live.
- Como control del pipeline legado, los 50 DXF devolvieron 422 `unsupported_geometry`: las vistas no respaldaron escenarios rectangulares coherentes.
- Los 3 PDF devolvieron 409 `normalized_dxf_unavailable` en el pipeline legado.

Por tanto, el resultado real es ingesta y extracción parcial con abstención/revisión. No hubo propuesta general, despiece válido ni pieza confirmada. Los 201 de subida/run no se cuentan como éxito semántico.

### Histórico público

Se envió sin transformar `public_furniture_history_2026-11-14/historical_import.json` a `POST /api/v1/history/import/json`, primero con `dry_run=true` y luego como importación aislada. v1 y v2 consumieron exactamente el mismo SHA-256, coincidente con el manifiesto, y los mismos cuatro registros.

En v1, dry-run/import devolvieron 422 porque los registros usan `origin="published"` y esa captura solo aceptaba `actual|synthetic`; el listado quedó en cero. En v2, tras los cuatro cambios concurrentes identificados arriba, dry-run e import devolvieron 200 con `accepted=4`, `unchanged=0`, `rejected=0`, sin errores; `GET /api/v1/history` devolvió los cuatro registros. El contraste aísla el cambio de contrato/servicio sin alterar el payload ni arreglar el producto desde este trabajo.

El corpus se declara como presupuestos preliminares de un caso académico público, no actuals cerrados de ERP ni historial representativo de fábrica. Los valores retail están separados. La prueba no valida precios de forma independiente ni usa esos componentes como oráculo de la app.

## Evidencia y reproducción

Artefactos autoritativos externos:

- Resumen compacto versionado: [`app-summary.json`](../experiments/cross-dataset-2026-11-14/app-summary.json).
- `D:/Vexplorer-semantic-lab/cross-dataset/app-snapshot-v2/snapshot_provenance.json`: procedencia y hashes finales.
- `D:/Vexplorer-semantic-lab/cross-dataset/app-v2/request.json`: muestra y hashes de entrada.
- `D:/Vexplorer-semantic-lab/cross-dataset/app-v2/results.json`: métricas y clasificación por caso.
- `D:/Vexplorer-semantic-lab/cross-dataset/app-v2/raw/*.json`: respuestas completas de subida, run general, drawing, endpoint general y control legado.
- `D:/Vexplorer-semantic-lab/cross-dataset/app-v2/raw/history_import.json`: dry-run, import y listado.
- `D:/Vexplorer-semantic-lab/cross-dataset/app-v2/snapshot_stability.json`, `worker_process.json` y `execution_assessment.json`: estabilidad, proceso y alcance real de instrumentación.
- `app-snapshot`/`app` conservan v1 como contraste, no como referencia final.

Comando final:

```powershell
python -m tools.semantic_lab.probe_app run `
  --snapshot D:\Vexplorer-semantic-lab\cross-dataset\app-snapshot-v2 `
  --dataset-root <DATASET_ROOT> `
  --output-dir D:\Vexplorer-semantic-lab\cross-dataset\app-v2 `
  --python <APP_VENV_PYTHON>
```

## Límites

- Sin live por configuración incompleta; no se probó el LLM ni su capacidad de proponer componentes.
- Sin inspección visual humana de PDFs ni comparación con BOM/oráculos.
- Sin afirmación de exactitud dimensional, de identidad entre vistas, de cantidades, de aptitud de fabricación o de cobertura industrial.
- Las categorías CADBlock son etiquetas editoriales de selección, no verdad técnica.
- La rama fuente cambió tras la captura; para atribuir comportamiento a su estado posterior hace falta una nueva instantánea y repetir la prueba.
