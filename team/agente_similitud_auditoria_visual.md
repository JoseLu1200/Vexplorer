# Auditoría independiente de despiece complejo

Estado al 2026-11-14: protocolo ciego, scorer y casos preparados; no se ha llamado al proveedor para esta ronda.

## Entregado

- Scorer por ocurrencia con assignment óptimo, tolerancias preregistradas y penalización simétrica de faltantes y candidatos falsos.
- Solo puntúa BOM derivado y revisado; borradores y jobs fallidos permanecen en el informe pero no acreditan entrega.
- `linear_member` cuenta como pieza de corte. Solo hardware con autoridad de revisión queda fuera y se informa aparte.
- Custodia por SHA del bundle y por `case_id + split + SHA del DXF` contra la referencia privada.
- Cohorte desarrollo fija: `plank-030`, `plank-016`.
- Holdout reservado: `plank-066`, 17 ocurrencias, seleccionado de forma determinística sin resultado del modelo; no ejecutar antes de freeze y gate de desarrollo.
- Baseline local 300 s: 0/2 entregas terminales; no extrapolar a producción 600 s.

## Archivos

- `evaluation/complex_cutlist.py`
- `tools/capture_complex_cutlist_live.py`
- `tools/evaluate_complex_cutlist.py`
- `tests/test_complex_cutlist_evaluation.py`
- `tests/test_complex_cutlist_capture.py`
- `docs/EVALUACION_DESPIECE_COMPLEJO.md`
- `.runtime/complex-cutlist-eval/development-manifest.json`
- `.runtime/complex-cutlist-eval/holdout-manifest.sealed.json`

## Regla de ejecución

Esperar GO explícito. Ejecutar desarrollo completo con config 600 s y modelos congelados; evaluar las dos salidas sin excluir fallos. Solo si ambas superan todos los gates, abrir una vez el holdout y evaluarlo con el mismo motor/configuración. No devolver GT ni referencias a implementadores.
