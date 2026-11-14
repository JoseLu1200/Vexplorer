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
- Benchmark reservado puntuado y cerrado con referencia principal rev4 erratum
  y sensibilidad rev3. Ocho informes, doce comparaciones, resumen público y
  manifiesto de derivación viven bajo `.runtime/semantic-v2-results/`.

## Cambios realizados

- El F1 principal mide recuperación completa: roles, unidades y relaciones
  desconocidos cuentan como referencia no recuperada; `covered_only` conserva
  la calidad condicionada a la cobertura sin maquillar el agregado.
- Cobertura publica numerador/denominador; opcionales se separan de requeridos.
- Informes por split, proyectos y casos completos, sin IDs privados de proyecto.
- Comparación v2 liga el lote exacto mediante hash de escenario/entrada/split y
  no copia casos ni referencias.
- El reviewer por defecto del runner es `gpt-6.1-sol`.
- Un fallo de adaptación post-freeze quedó reproducido: varias aristas por
  ocurrencia física colapsaban a la misma tripleta de rol. Se deduplican
  tripletas exactas tras proyectar IDs a roles, también en alternativas. Los
  outputs nativos no se mutaron; se regeneraron ambos manifiestos semánticos
  con la misma revisión y se registró la cronología.

## Resultado reservado principal

- Cohorte: 30 planos, seis topologías holdout por cinco perfiles; no son 30
  diseños independientes. Ambos runs Sol/Sol completaron 30/30 sin fallos.
- Original reviewed: roles F1 0,2184; ocurrencias F1 0,1972; relaciones F1 0;
  0/30 casos completos.
- Corrected reviewed: roles F1 0,2543; ocurrencias F1 0,2529; relaciones F1 0
  con 90 falsos positivos; 0/30 casos completos.
- Rev3→rev4 no cambia roles/ocurrencias ni el F1 de relaciones, pero aumenta
  FN de relaciones 35→50 (original) y 20→50 (corrected). Rev4 es principal.
- Diagnóstico: mezcla de desalineación ontológica y subrecuperación real; no
  se añadieron aliases ni se retocó la referencia después de ver scores.

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
- Verificación final propia: `26 passed`; Ruff `All checks passed!`;
  `compileall` y `git diff --check` exit 0.
- Verificación global de raíz: `793 passed`; combo corpus/evaluación `51 passed`.
- Manifiesto recalculado: 8/8 hashes de informe, referencia fuente y sello
  coinciden; `Issues=0`.
