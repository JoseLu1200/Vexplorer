# Agente semántica v2 — evaluación y benchmark

## Identidad y autorización

- Identidad: agente de IA delegado; no representa a una persona.
- Rol: auditar y corregir la evaluación semántica offline sin modificar el runtime.
- Archivo creado por autorización explícita de `/root` el 2026-11-14.

## Tarea y alcance

- Objetivo: impedir que desconocidos o abstenciones maquillen F1, cubrir roles, cantidades y relaciones, preservar independencia y freeze de referencias, y ejecutar baseline/final sobre el corpus ampliado disponible.
- Propiedad: `evaluation/semantic.py`, `tools/evaluate_semantic.py`, `tools/seal_semantic_reference.py`, pruebas semánticas y de sellado, este registro.
- Disponible si resulta necesario: `tools/run_general_benchmark.py` y sus pruebas, coordinando cualquier cambio con dataset.
- Solo lectura: runtime, contratos, referencias privadas y registros ajenos.
- No se copiarán secretos, respuestas privadas ni detalles de oráculo a rutas visibles por implementadores o proveedor.

## Estado

- Métricas y comparador v2 implementados por TDD y congelados funcionalmente.
- Pendiente puntuar los freezes original/corregido del holdout nuevo cuando
  raíz confirme ambas ejecuciones; no se ha abierto la referencia privada.

## Cambios realizados

- El F1 principal mide recuperación completa: roles, unidades y relaciones
  desconocidos cuentan como referencia no recuperada; `covered_only` conserva
  la calidad condicionada a la cobertura sin maquillar el agregado.
- Cobertura publica numerador/denominador; opcionales se separan de requeridos.
- Informes por split, proyectos y casos completos, sin IDs privados de proyecto.
- Comparación v2 liga el lote exacto mediante hash de escenario/entrada/split y
  no copia casos ni referencias.
- El reviewer por defecto del runner es `gpt-6.1-sol`.

## Dependencias / avisos

- Coordinar corpus, splits y artefactos públicos con dataset antes de ejecutar un benchmark ampliado.
- Las métricas finales deben publicar denominadores, cobertura y recuperación completa, además de F1.
- Cambio de `contratos/`: no aplica.

## Pruebas y verificación

- Baseline focal previo: `26 passed`.
- RED: 6 fallos demostraron unknown fuera de FN, FP oculto por unknown global,
  ausencia de splits y reviewer Astra; RED adicionales cubrieron opcionales,
  alternativas, conteos de proyecto, comparación CLI y cohortes distintas.
- GREEN focal fresco: `.venv\Scripts\python.exe -m pytest -q tests/test_semantic_evaluation.py tests/test_run_general_benchmark.py tests/test_prepare_semantic_corpus.py` → `47 passed`.
- `compileall` de evaluador y CLIs → exit 0. El Python de sistema aporta
  Ruff 0.15.20: `python -m ruff check <rutas propias>` → `All checks passed!`.
- `git diff --check` sin errores; solo avisos de conversión LF/CRLF en dos
  archivos existentes.
- Suite global y benchmark live coordinados por raíz para no duplicar procesos.
