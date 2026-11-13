# Agente de evaluación — fixture y oráculo

## Identidad y autorización

- Identidad: agente de IA responsable del fixture sintético y la evaluación reproducible de la demo.
- Rol: D, evaluación.
- Archivo autorizado explícitamente por el usuario: `team/agente_evaluacion.md`, 2026-11-13.
- El usuario autoriza decisiones autónomas dentro del ámbito, sin despliegue ni `push`.

## Tarea y alcance

- Estado: en curso para la entrada parts-only 0.4 del 2026-11-14.
- Propiedad: `data/planos_demo/`, `evaluation/`, `tools/build_demo_fixture.py`, `tests/test_demo*.py` y este archivo.
- Propiedad adicional autorizada: `tools/build_parts_fixture.py`, `data/planos_demo/piezas_*`, `evaluation/reference/piezas_*` y `tests/test_parts_only_evaluation.py`.
- Solo lectura/coordinación: contratos, geometría, backend, frontend y documentación compartida.
- Solapes comprobados: ninguno; la propiedad está registrada en `team/agente_coordinador.md`.
- Objetivo actual: fixture propio compuesto solo por vistas locales de piezas separadas, cantidades públicas asociadas cuando existan, variantes con incógnitas y controles de descriptor, manteniendo ensamblaje/roles/BOM exclusivamente en referencia privada.

## Hecho

- Creado bloque parts-only público con siete DXF propios: completo, cantidad desconocida, espesor desconocido, dimensiones distintas, espesor 36 mm, claves/traslación distintas y vistas ambiguas sin clave.
- La gramática visible usa `PART <key> FRONT|TOP|SIDE` y `QTY <key> <n>`; FRONT=(L,W), TOP=(L,T), SIDE=(T,W). Un `QTY` suelto no se asocia.
- Separada la nueva referencia de ensamblaje, roles y economía en `evaluation/reference/piezas_reference.json`; el generador no la importa ni la lee.
- Neutralizado el manifiesto público tras detectar que sus propósitos describían faltas de evidencia; todos los casos comparten ahora una descripción genérica.
- El control t36 conserva la misma envolvente derivable de 900 mm mediante horizontales de 828 mm; diferencia espesor sin confundirlo con un cambio exterior.
- La referencia privada conserva ambigüedad de permutación de roles K2/K3, no reclama `cap_sides`: con dos horizontales de 864 mm esa disposición no es dimensionalmente compatible.
- Creado fixture propio de estantería rectangular montada, en DXF R2010 y mm, con vistas `FRONT`, `TOP`, `RIGHT`, cotas generales y sin nombres de piezas/BOM.
- Creada variante incompleta que elimina evidencia de espesor y exige conservarlo desconocido.
- Separada la construcción revisada en `evaluation/reference/`, con dos escenarios plausibles y política que no reclama solución única.
- Acordada con A la gramática pública; A no leerá referencia/sidecars y normalizará `RIGHT` a vista lateral.
- Acordado con B que observaciones son inmutables, escenarios son hipótesis y revisión humana confirma montaje/espesor/cantidad. B declaró `ezdxf` en su contrato integrado.
- Corregido el estilo de cotas a `Standard` con `DIMLFAC=1`; el estilo `EZDXF` incorporaba un factor 100 incompatible con la entrada en mm.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-11-13 | Fixture original, no derivado de PlankAssembly ni corpus mecánico | Evitar restricciones/licencias y mantener un oráculo independiente |
| 2026-11-13 | Capas públicas neutrales y referencia solo del evaluador | Evitar fugas a extractor, prompt, herramientas y endpoints |
| 2026-11-13 | Tres vistas no equivalen a cantidad; referencia revisada suma siete ocurrencias | Probar identidad/conteo de forma independiente |
| 2026-11-13 | PlankAssembly queda como tarea futura separada y acotada | CC BY-NC-ND 4.0, adaptación y vistas 2D siguen pendientes |
| 2026-11-13 | Biblioteca pública parametrizada con nombres opacos para dos variantes y controles negativos | Evaluar geometría/estructura sin usar IDs o respuestas privadas como señal |
| 2026-11-13 | Unidad desconocida y trapecio son casos de preview, no casos de despiece | El plano debe seguir visible aunque la inferencia se abstenga |

## Dependencias / avisos

- B entregará la API vertical para ejecutar el E2E TestClient de revisión, comparable, estimación y exportación.
- La referencia privada nunca se comunica al extractor ni se incorpora a prompts, endpoints, herramientas, índice histórico o runtime.
- No hay cambio de `contratos/` por D.
- Nueva fase: A/B deben comunicar el contrato aditivo de escena, descriptor/similitud y agrupación antes de cerrar las pruebas E2E; D no escribirá esos contratos ni duplicará sus pruebas unitarias.
- Los fixtures nuevos solo comunican vistas/cotas públicas. BOM, montaje de referencia y grupos esperados del evaluador permanecen fuera del runtime.
- Parts-only 0.4: A/B acordaron claves opacas y ejes locales; D espera el hash contractual materializado antes de fijar pruebas de integración. No se agrupa por proximidad ni se infiere cantidad desde el número de vistas.

## Pruebas

| Caso | Comando | Resultado observado | Limitación |
|---|---|---|---|
| TDD rojo | `python -m pytest tests/test_demo_fixture.py tests/test_demo_isolation.py -q` | 7 fallos, 1 pasa antes de generar DXF/manifiesto | Dependencia ezdxf instalada tras declaración de B |
| Fixture e aislamiento reproducible | mismo comando tras generar | 9 pasan; dos procesos generan bytes idénticos | Todavía sin backend integrado |
| E2E rojo previo a integración | `python -m pytest tests/test_demo_e2e.py -q` | error de colección esperado: backend agéntico/API aún ausente en esta rama | Resuelto al integrar B |
| E2E contra API real integrada | desde raíz: `.venv\Scripts\python.exe -m pytest .worktrees/evaluacion/tests/test_demo_e2e.py -q` | 2 pasan; 1 aviso deprecación TestClient/httpx | Oráculo económico manual suma todas las piezas: 127,84 EUR |
| Suite D integrada | desde raíz: `.venv\Scripts\python.exe -m pytest tests/test_demo_fixture.py tests/test_demo_isolation.py tests/test_demo_e2e.py -q` | 11 pasan; 1 aviso deprecación | Incluye aislamiento estático y dinámico |
| Suite Python integrada | desde raíz: `.venv\Scripts\python.exe -m pytest -q` | 52 pasan; 1 aviso deprecación tras hardening del bundle | No se ejecutó navegador; corresponde al coordinador |
| Biblioteca parametrizada, TDD rojo | `.venv\Scripts\python.exe -m pytest tests/test_demo_fixture.py -q` | 9 fallos por fixtures/referencia aún ausentes; 8 pasan | Fallo esperado antes de implementar |
| Biblioteca parametrizada e aislamiento | `.venv\Scripts\python.exe -m pytest tests/test_demo_fixture.py tests/test_demo_isolation.py -q` | 19 pasan | API 0.3 aún no integrada en esta rama |
| Control de invariancia, TDD rojo | `.venv\Scripts\python.exe -m pytest tests/test_demo_fixture.py -q` | 5 fallos por control trasladado ausente; 15 pasan | Fallo esperado antes de implementar |
| Biblioteca con traslación | `.venv\Scripts\python.exe -m pytest tests/test_demo_fixture.py tests/test_demo_isolation.py -q` | 22 pasan | Descriptor/API pendientes de B |
| Aceptación preview/escena, TDD rojo | `.venv\Scripts\python.exe -m pytest tests/test_demo_workbench.py -q` | 3 fallos HTTP 404 esperados | Endpoints 0.3 todavía no integrados |
| Aceptación biblioteca/similitud, TDD rojo | mismo comando tras ampliar | 4 fallos 404/405 esperados | API escena/biblioteca todavía no integrada en esta rama |
| Aceptación 0.3 contra backend candidato | desde la rama B: `.venv\Scripts\python.exe -m pytest .worktrees/evaluacion/tests/test_demo_workbench.py -q` | 4 pasan; 1 aviso deprecación | Falta repetir tras integrar el commit B en raíz |
| Suite D contra backend candidato | fixture, aislamiento, E2E previo y workbench | 28 pasan; 1 aviso deprecación | Verificación cruzada; no sustituye la suite final en raíz |
| Suite D en raíz integrada | fixture, aislamiento, E2E previo y workbench | 28 pasan; 1 aviso deprecación | Backend, escena, biblioteca y tests D integrados |
| Suite Python en raíz integrada | `.venv\Scripts\python.exe -m pytest -q` | 113 pasan; 1 aviso deprecación | Incluye hardening de argumentos nativos; no incluye JavaScript ni navegador |
| Parts-only TDD rojo | `python -m pytest tests/test_parts_only_evaluation.py -q` antes del generador | 14 fallos por DXF, manifiesto, módulo y referencia ausentes | Fallos esperados del nuevo bloque |
| Parts-only fixture + aislamiento | `python -m pytest tests/test_parts_only_evaluation.py tests/test_demo_isolation.py -q` | 17 pasan | API 0.4 todavía no integrada; solo contrato público de entrada y aislamiento |
| Manifiesto neutral TDD | test focalizado antes/después de eliminar propósitos diagnósticos | 1 fallo esperado, después 1 pasa | Filenames de demo permanecen; no entran al modelo/descriptor |
| Aceptación 0.4 TDD roja | `python -m pytest tests/test_parts_only_evaluation.py -q` | 15 pasan; 4 fallan porque la API 0.3 rechaza `input_kind` | Fallo esperado previo a integrar extractor/orquestación/API 0.4 |
| Aceptación 0.4 contra backend candidato | desde rama B HEAD `81efa93`: parts-only | 19 pasan; 1 aviso deprecación | TestClient real; referencia privada bloqueada durante runtime |
| Suite D contra backend candidato 0.4 | parts-only + fixtures/aislamiento/E2E/workbench legacy | 47 pasan; 1 aviso deprecación | Falta repetir sobre raíz integrada y HTTP real 8768 |

## Siguiente bloque

- Compartir el commit temprano de fixtures con A/B sin revelar la referencia privada.
- Tras recibir el hash contractual 0.4, añadir aceptación de observaciones, trazabilidad, revisión, descriptor, escena y economía sin duplicar pruebas unitarias A/B.
- Ejecutar suites completas sobre la raíz integrada; sin despliegue ni `push`.

## Cierre de la fase anterior

- Entrega completada dentro de las rutas asignadas; sin despliegue, `push` ni datos de terceros.
- El E2E exige que la exportación JSON sea una ficha completa y coherente de la revisión: resultado, comparables, estimación y eventos.
- Pendiente del coordinador: recorrido de navegador real y cualquier validación con técnico. Este fixture de desarrollo no acredita precisión industrial ni benchmark ciego.

