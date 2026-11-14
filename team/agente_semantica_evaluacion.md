# Agente de evaluación semántica — laboratorio aislado

## Identidad y autorización

- Identidad: agente de IA de evaluación semántica; no representa a una persona.
- Autorización explícita del usuario, 2026-11-14: swarm GPT-6.1 Sol para el experimento y revisión final GPT-6 Astra.
- Archivo propio nuevo indicado por la coordinación para esta tarea.

## Tarea de la sesión

- Objetivo: implementar un evaluador CLI reproducible y un CLI de consulta para el manifiesto `schema_version: 1` del laboratorio semántico.
- Referencias: `docs/superpowers/specs/2026-11-14-semantic-lab.md` y plan correspondiente.
- Estado: implementación terminada; test final permanece sellado para la comparación aprendida.

## Alcance y reservas

- Propiedad exclusiva: `tools/semantic_lab/evaluate.py`, `tools/semantic_lab/query.py`, `tests/test_semantic_lab_evaluate.py` y este registro.
- Ampliación autorizada: `tools/semantic_lab/classifier_comparison.py`, `tests/test_semantic_lab_classifier_comparison.py`, `docs/semantic-lab/COMPARACION_CLASIFICADORES_LOCALES.md` y `docs/experiments/classifier-comparison-2026-11-14/local-summary.json`.
- Solo lectura: resto del repositorio, manifiestos y artefactos externos que aporte coordinación.
- No instalar dependencias, no modificar contratos/producto, no hacer commits ni escribir reportes de ejecución dentro de Git.
- Solapes comprobados: ninguno; el coordinador semántico posee integración/dependencias y otros agentes tienen archivos distintos bajo `tools/semantic_lab/`.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-11-14 | Ajuste y selección exclusivamente con train/validation; test requiere subcomando y consentimiento explícito | Evitar uso accidental del reservado |
| 2026-11-14 | Etiquetas y categorías se usan solo para métricas proxy, nunca para construir vectores | Evitar leakage |
| 2026-11-14 | Artefactos, configuración congelada, informes e índice se escriben solo en `--output-dir` | Mantener datos/resultados fuera de Git |
| 2026-11-14 | Cada NPZ aprendido se nombra con `--embedding NAME=PATH` y su SHA-256 entra en la configuración congelada | Comparar modelos sin sustituir vectores entre validación y test |
| 2026-11-14 | Objetivos de piloto: macro-F1 0,70 y balanced accuracy 0,75 en validación | Pre-registro orientativo; no certifica utilidad industrial |
| 2026-11-14 | Futuras aperturas de test exigen `validation-report.json` adyacente con hash canónico del frozen config y coherencia del ganador | Hallazgo de revisión Astra; los artefactos finales históricos se generaron antes de esta guarda y no se reescriben |
| 2026-11-14 | Primera interpretación: core train/validation y 14 CAD extra forzados | Sustituida antes de fit o métricas; no se ejecutó ni se puntúa |
| 2026-11-14 | Protocolo local v2 sustituye el anterior antes de fit: kNN EG2, core/CAD extra separados y engineering como OOD forzado | Aclaración de coordinación; la versión anterior quedó sin ejecutar ni puntuar |

## Dependencias / avisos

- Necesito de coordinación: NumPy/scikit-learn declarados e instalados; HDBSCAN queda opcional según disponibilidad comprobada.
- Afecta a: agente que preparará el manifiesto/representaciones y coordinador que ejecutará selección/test.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| Baseline de dependencias | `Vexplorer/.venv/Scripts/python.exe -c "import numpy, sklearn"` | falla: `ModuleNotFoundError: sklearn` | coordinación instalará scikit-learn; este agente no instala dependencias |
| TDD inicial | `python -m pytest tests/test_semantic_lab_evaluate.py -q` | error esperado: módulo ausente | Antes de implementar |
| Regresiones focales | `python -m pytest tests/test_semantic_lab_evaluate.py -q` | 13 passed | Python global con NumPy/scikit-learn |
| Estática | `compileall`, `python -m ruff check ...`, `git diff --check ...` | correcto; Ruff `All checks passed!` | Rutas propias |
| Suite integrada final | `python -m pytest -q` | 461 passed en 96,07 s | Ejecución fresca tras todos los cambios; incluye trabajo concurrente visible |
| Selección baseline | `python -m tools.semantic_lab.evaluate select --manifest D:/Vexplorer-semantic-lab/data/core/manifest.json --output-dir D:/Vexplorer-semantic-lab/results/baseline-select --representations geometry text geometry+text --classifiers knn centroid logreg --clusterers kmeans hdbscan --cluster-counts 2 3 4 5 --pca-components 2 4 8 --neighbors 5 --retrieval-k 5 --seed 0` | validación: geometry+text, kNN-5, sin PCA; macro-F1 0,9143, balanced accuracy 0,9167, precision@5 0,8588, hit@5 1,0. KMeans-5: ARI 0,4171, NMI 0,6970, pureza 0,8235, cobertura 1,0 | Etiquetas editoriales proxy; 17 casos validation; test no evaluado |
| Guarda post-revisión | `python -m pytest tests/test_semantic_lab_evaluate.py -q` | 16 passed | RED previo: 3 fallos por config editable/informe ausente/ganador inconsistente; GREEN incluye matriz, por-clase e IDs erróneos para futuras corridas |
| Estática post-revisión | `python -m ruff check ...`; `compileall`; `git diff --check` | correcto | No se tocaron ni reejecutaron artefactos reales de validation/test |
| Suite integrada post-revisión | `python -m pytest -q` | 466 passed en 48,94 s | Sin acceso a artefactos reales |
| Comparación local, TDD | `python -m pytest tests/test_semantic_lab_classifier_comparison.py -q` | RED por módulo ausente; ampliado tras hallazgos de artefacto/resumen | Cubre grid fijo, fit train-only, kNN sin geometría, OOD fijo, desempate, schemas, resumen y carga en proceso nuevo |
| Estática comparación | `ruff`, `compileall`, `git diff --check` sobre rutas nuevas | correcto | Sin suite global por instrucción de coordinación |
| Core retrospectivo | CLI de `classifier_comparison` | kNN EG2: validation F1/BA 1,0/1,0; test post hoc 0,8261/0,8333 | Iguala baseline conocido; no es nuevo blind |
| CAD extra retrospectivo | misma corrida | logreg C=0,1: validation 0,8838/0,8956; test post hoc 0,8445/0,8604 | +0,0665 F1 frente a baseline conocido 0,778; comparación post hoc |
| Engineering forzado | ganador core sobre 14 muestras | 11 buffets, 2 sofas, 1 simple-tables | No mide acierto OOD ni calibra review |
| Artefactos reutilizables | carga Joblib desde proceso nuevo | core `knn_eg2_k5`; CAD extra `logreg_combined_c0.1` | Sólo artefactos propios; no cargar pickle externo |
| Verificación focal final | `python -m pytest tests/test_semantic_lab_classifier_comparison.py -q`; Ruff; compileall; JSON parse; diff-check | 9 passed; estática correcta | No se repitieron métricas; root ejecutará suite global |

## Bloqueos y cierre

- Bloqueos: ninguno para el evaluador.
- Pendientes: comparar embeddings aprendidos en validation y abrir test una vez con el ganador global; lo ejecutará coordinación.
- Reservas liberadas: ninguna.
