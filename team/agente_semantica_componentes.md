# Agente de similitud constructiva — laboratorio aislado

## Identidad y autorización

- Identidad: agente de IA de similitud constructiva; no representa a una persona.
- Autorización explícita del usuario, 2026-11-14: swarm GPT-6.1 Sol para experimentar con clasificación/embeddings y similitud de muebles orientada a comparables de coste, con revisión final GPT-6 Astra.
- Archivo propio y alcance designados explícitamente por coordinación en esta sesión.

## Tarea de la sesión

- Implementar una comparación experimental de composición constructiva para `FurnitureDescriptorV2`/`V3` ya producidos por el harness.
- Entregar `compare_components(left, right) -> dict` con score, cobertura, contribuciones y diferencias explicables, además de un control sintético CLI fuera de Git.
- Estado: implementado y verificado; pendiente integración/revisión del coordinador.

## Alcance y reservas

- Propiedad exclusiva: `tools/semantic_lab/components.py`, `tests/test_semantic_lab_components.py` y este registro.
- Solo lectura: contratos/descriptores del producto, especificación, plan y fixtures públicos de desarrollo.
- Fuera de alcance: contratos y runtime del producto, referencias reservadas, archivos de otros agentes, dependencias, commits y despliegue.
- Solapes comprobados: ninguno; otros agentes reservan archivos distintos bajo `tools/semantic_lab/`.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-11-14 | Comparar multiconjuntos agregados por rol y dimensiones, sin expandir cantidades | Respetar cantidades y evitar consumo proporcional a cantidades gigantes |
| 2026-11-14 | Separar similitud observada de cobertura de evidencia | Un desconocido no equivale a cero ni puede producir coincidencia perfecta |
| 2026-11-14 | Control exclusivamente sintético y rotulado | No afirmar exactitud real ni abrir referencias reservadas |
| 2026-11-14 | Roles conocidos incompatibles no se pueden emparejar | Evitar que piezas geométricamente iguales intercambien función constructiva |
| 2026-11-14 | Los roles V3 repetidos se agregan por suma, no por sobrescritura | La representación agrupada/desagrupada del mismo multiconjunto debe ser invariante |
| 2026-11-14 | Cantidad V2 desconocida usa peso unitario de observación y se etiqueta como no físico | No convertir ausencia de cantidad en una unidad material aparente |
| 2026-11-14 | Transporte con objetivo lexicográfico: máxima masa compatible y luego máxima afinidad | Un par de afinidad cero debe conservarse para exponer diferencias conocidas; roles incompatibles siguen prohibidos |

## Dependencias / avisos

- SciPy global está disponible; se permite `linear_sum_assignment`.
- Afecta solo al laboratorio aislado; no cambia contratos ni resultados del producto.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| RED inicial | `python -m pytest tests/test_semantic_lab_components.py -q` | error esperado: módulo ausente | Antes de implementar |
| RED roles | prueba focal `test_known_roles_cannot_exchange_quantities_even_when_geometry_matches` | fallo esperado: emparejaba 3 en vez de 2 | Corregido restringiendo transporte por rol conocido |
| Suite focal y regresión semántica | `python -m pytest tests/test_semantic_lab_components.py backend/tests/test_backend_semantic.py backend/tests/test_production_semantic.py -q` | 18 passed | No mide exactitud real |
| Lint | `python -m ruff check tools/semantic_lab/components.py tests/test_semantic_lab_components.py` | All checks passed | Solo archivos propios de código |
| Suite completa | `python -m pytest -q` | 454 passed, 3 failed | Fallos ajenos concurrentes: `test_semantic_lab_dataset.py` (1) y `test_semantic_lab_evaluate.py` (2) |
| Control | `python -m tools.semantic_lab.components control --output D:/Vexplorer-semantic-lab/components-control.json` | JSON escrito; scores 1.0 / 0.884298 / 0.8125 / 0.9 | Control sintético, no accuracy ni equivalencia de costes |
| RED revisión coordinador | `python -m pytest tests/test_semantic_lab_components.py -q` | 2 fallos esperados: falta de etiqueta de cantidad desconocida y score agrupado 0.925 | Antes de corregir `_role_profile` y reporte matching |
| Focal posterior a revisión | `python -m pytest tests/test_semantic_lab_components.py -q` | 10 passed | Incluye invariancia agrupado/desagrupado y simetría score/coverage |
| Lint posterior a revisión | `python -m ruff check tools/semantic_lab/components.py tests/test_semantic_lab_components.py` | All checks passed | Sin cambio de pesos |
| RED hallazgo Astra | prueba focal `test_zero_affinity_v2_observations_still_match_to_expose_known_material_difference` | fallo esperado: `matched_quantity` 0 en vez de peso de observación 1 | Confirmó que LP de afinidad ocultaba material conocido distinto |
| Focal posterior a Astra | `python -m pytest tests/test_semantic_lab_components.py -q` | 11 passed | Incluye masa cero-afinidad, rol incompatible y no contabiliza cantidad desconocida como física |

## Bloqueos y cierre

- Bloqueos: suite global actualmente roja por tres fallos en archivos reservados a los agentes de datos/evaluación; la regresión propia y semántica pasa.
- Pendientes: integración y revisión final GPT-6 Astra por coordinación.
- Reservas liberadas: los tres archivos propios quedan listos para transferencia al coordinador.
