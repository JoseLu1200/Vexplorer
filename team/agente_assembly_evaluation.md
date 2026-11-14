# assembly_evaluation — evaluación independiente de montaje

## Identidad y autorización

- Nombre declarado por el coordinador: `assembly_evaluation`
- Rol: evaluador geométrico offline independiente
- Archivo creado o designado explícitamente: delegación de `/root`, 2026-11-14
- Última actualización: 2026-11-14

## Tarea de la sesión

- Objetivo concreto: comparar montajes por ocurrencia con una sola alineación global ortogonal propia, biyección, errores métricos, orientación y penetraciones.
- Referencia: `docs/superpowers/specs/2026-11-14-general-assembly-design.md`
- Estado: terminado

## Alcance y reservas

- Archivos editados: `evaluation/assembly.py`, `tests/test_assembly_evaluation.py`, `tools/evaluate_assembly.py`, este registro.
- Dependencias solo leídas: contrato de core, preparación PlankAssembly y evaluadores existentes.
- Solapes: ninguno; el adaptador se coordinó con `assembly_core` y consume `placements` sin modificar su contrato.

## Hecho

- Normalización explícita del formato canónico y de `GeneralAssemblyValidationReport.placements`: `position_mm` como mínimo AABB mundial, `size_mm` como extensiones mundiales y orientación `+x/-x/...`.
- Búsqueda determinista sobre las 24 rotaciones ortogonales propias, una traslación global y asignación húngara biyectiva sin SciPy.
- Métricas por ocurrencia de dimensiones, centros, caras, normal de panel, diagonal normalizada, reproyección ortográfica, cobertura y penetración no explicada.
- Penetración absoluta candidata y de referencia se informa por separado de la penetración adicional; superar la primera impide certificar que la geometría sea libre de colisiones aunque satisfaga el criterio relativo a referencia.
- Simetrías geométricas de cajas aceptadas; reflexiones globales, faltantes, extras y recolocación/reorientación local rechazadas.
- Frontera de fichero vinculada por SHA-256: se congela y lee la predicción antes de abrir la referencia privada. CLI con escritura atómica.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-11-14 | Aceptar ejes locales equivalentes mediante permutación coherente dimensión/eje y signo de normal | Una caja no distingue signos de caras y un panel cuadrado no distingue el giro en su plano |
| 2026-11-14 | Exigir determinante +1 tanto en marcos de pieza como en la alineación global | Impide que una reflexión se disfrace de rotación |
| 2026-11-14 | Comparar penetración candidata contra penetración ya presente en referencia | Reporta solo penetración adicional no explicada |

## Pruebas y revisión

| Caso | Comando | Resultado observado |
|---|---|---|
| Regresión unitaria | `.venv\\Scripts\\python.exe -m pytest tests/test_assembly_evaluation.py -q` | 17 passed |
| Integración core + evaluator | `.venv\\Scripts\\python.exe -m pytest tests/test_assembly_evaluation.py backend/tests/test_general_furniture_assembly.py backend/tests/test_general_furniture_assembly_live.py backend/tests/test_general_furniture_assembly_semantics.py -q` | 57 passed; 1 warning deprecación externo |
| Suite completa | `.venv\\Scripts\\python.exe -m pytest -q` | 791 passed; 2 warnings deprecación externos |
| Estática | `python -m ruff check evaluation/assembly.py tools/evaluate_assembly.py tests/test_assembly_evaluation.py` | All checks passed |

## Bloqueos y cierre

- Bloqueos: ninguno.
- Pendiente externo: ejecutar el caso privado real después de congelar su salida y vincular `prediction_sha256`; no se usó la referencia para ajustar el runtime.
- Cambio de `contratos/`: no aplica.
