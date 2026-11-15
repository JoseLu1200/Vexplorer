# Agente de correcciones PR/CI — evaluación

## Identidad y autorización

- Nombre declarado por el usuario: agente IA `fix_evaluation`, sin identidad humana atribuida.
- Rol: correcciones acotadas de evaluación y corpus.
- Archivo creado o designado explícitamente: solicitado por coordinación bajo autorización absoluta del usuario, 2026-11-14.
- Última actualización: 2026-11-15.

## Tarea de la sesión

- Objetivo concreto: aislar el DXF entregado a cada método y detectar mutaciones; evitar falsos negativos del índice de candidatos PlankAssembly dentro de tolerancia.
- Referencia del plan: revisión PR/CI, dos hallazgos P1.
- Estado: terminado.

## Alcance y reservas

- Archivos que puedo editar: `evaluation/comparativa/runner.py`, `evaluation/comparativa/manifest.py` si resulta necesario, `tools/plankassembly_corpus.py`, `tests/test_comparativa_metodos.py`, `tests/test_plankassembly_corpus.py` y este registro.
- Dependencias que solo leeré: contratos y helpers importados por esos módulos.
- Archivos compartidos que requieren coordinación: ninguno dentro de la reserva delegada.
- Solapes detectados y acuerdo para resolverlos: el alcance histórico de `team/pablo.md` incluye estas rutas; coordinación delegó explícitamente estas correcciones en la rama de integración.

## Hecho en el último bloque

- Cada invocación recibe una copia temporal independiente del `PublicCase`; se verifican SHA-256 declarado, copia y fuente antes/después, y una mutación queda como `failed:input_mutated`.
- El índice de candidatos usa rangos inclusivos deterministas sobre una dimensión ancla y su razón normalizada; `_cercanos` conserva la decisión final sin falsos negativos en la frontera de tolerancia cubierta.
- Añadidas regresiones de mutación/aislamiento y de vecinos a 2 mm dentro de una partición y entre particiones.

## Siguiente bloque

- Entregar a coordinación para integrar; no hay cambios pendientes en la reserva.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | No modificar contratos ni rutas ajenas | La corrección está delimitada a evaluación/corpus | Delegación de coordinación |
| 2026-11-15 | Usar búsquedas de rango y verificar con `_cercanos` | Evita combinaciones exponenciales de celdas vecinas sin perder pares dentro del criterio | Regresiones roja/verde en ambas particiones |

## Dependencias / avisos

- Necesito de: ninguna dependencia externa ni red.
- Afecta a: ejecución comparativa y agrupación del corpus PlankAssembly.
- Aviso realizado: entrega final al coordinador con comandos y resultados.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Rojo: aislamiento | `..\Vexplorer\.venv\Scripts\python.exe -m pytest tests/test_comparativa_metodos.py::test_each_method_gets_an_isolated_input_and_mutation_fails -q` | 1 fallo esperado: mutador figuraba `ok` | sin red |
| Rojo: fronteras | `..\Vexplorer\.venv\Scripts\python.exe -m pytest tests/test_plankassembly_corpus.py -k "indice_no_pierde_vecinos_en_fronteras_de_rejilla" -q` | 2 fallos esperados: ambos vecinos sobrevivían | sin dataset externo |
| Regresiones finales | selección de cuatro casos críticos con `pytest -q` | 4 passed | sin red |
| Suite afectada | `..\Vexplorer\.venv\Scripts\python.exe -m pytest tests/test_comparativa_metodos.py tests/test_plankassembly_corpus.py -q -p no:cacheprovider --basetemp ..\pr-ci-eval-tmp` | 115 passed en 27.50 s | temporal exclusivo; sin red/proveedor/dataset |
| Ruff | `..\Vexplorer\.venv\Scripts\python.exe -m ruff check ...` | no ejecutable: `No module named ruff` | dependencia ausente en el entorno compartido |

## Bloqueos y cierre

- Bloqueos: ninguno para la corrección; Ruff no está instalado en el entorno indicado.
- Pendientes: integración por coordinación.
- Reservas liberadas: rutas delegadas, 2026-11-15.
- Entrega a otra persona: coordinación de la rama de integración.
