# Agente de evaluación — fixture y oráculo

## Identidad y autorización

- Identidad: agente de IA responsable del fixture sintético y la evaluación reproducible de la demo.
- Rol: D, evaluación.
- Archivo autorizado explícitamente por el usuario: `team/agente_evaluacion.md`, 2026-11-13.
- El usuario autoriza decisiones autónomas dentro del ámbito, sin despliegue ni `push`.

## Tarea y alcance

- Estado: auditoría independiente de API HTTP real del 2026-11-14, sin modificar producto.
- Propiedad: `data/planos_demo/`, `evaluation/`, `tools/build_demo_fixture.py`, `tests/test_demo*.py` y este archivo.
- Propiedad adicional autorizada para esta auditoría: `tools/audit_api.py` y `docs/auditoria/2026-11-14/api.json`.
- Solo lectura/coordinación: contratos, geometría, backend, frontend y documentación compartida.
- Solapes comprobados: ninguno; la propiedad está registrada en `team/agente_coordinador.md`.
- Objetivo actual: ejecutar carga, preview, inferencia geométrica, revisión, historial, escena, economía, biblioteca y errores mediante HTTP real contra una instancia aislada; producir evidencia JSON saneada y reproducible.

## Hecho

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
- La auditoría usa exclusivamente fixtures públicos y no habilita proveedor real. El coordinador administra la instancia aislada en `127.0.0.1:8767` y su runtime; D no corrige hallazgos durante la auditoría.

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
| Primer pase auditoría HTTP | `python tools/audit_api.py --base-url http://127.0.0.1:8767` | 61 pasan, 3 hallazgos encadenados | La revisión de auditoría usó material/acabado fuera del catálogo sintético; estimación 422, export sin estimación y sin evento económico. No fue fallo de producto |
| Auditoría HTTP final | mismo comando tras usar la premisa pública compatible | 64 pasan, 0 fallan; evidencia en `docs/auditoria/2026-11-14/api.json` | `geometry_only` y embeddings offline; ningún proveedor real ni referencia privada |
| Suite Python de auditoría | `..\..\.venv\Scripts\python.exe -m pytest -q` | 119 pasan; 1 aviso deprecación | La primera ejecución detectó la ruta privada literal en el runner; se eliminó de la superficie runtime y se repitió completa |
| Suite JavaScript de auditoría | `npm test --prefix frontend` | 46 pasan, 0 fallan | Pruebas automatizadas; el recorrido de navegador corresponde al coordinador |

## Siguiente bloque

- Entregar al coordinador el runner, la evidencia saneada y los IDs observados, sin corregir producto ni hacer `push`.
- Registrar como no implementado el nuevo objetivo de entrada compuesta solo por vistas separadas de piezas, sin mueble montado.
- Esperar el contrato exacto A/B antes de crear el futuro fixture de piezas, sus variantes u oráculos.

## Cierre de la fase anterior

- Entrega completada dentro de las rutas asignadas; sin despliegue, `push` ni datos de terceros.
- El E2E exige que la exportación JSON sea una ficha completa y coherente de la revisión: resultado, comparables, estimación y eventos.
- Pendiente del coordinador: recorrido de navegador real y cualquier validación con técnico. Este fixture de desarrollo no acredita precisión industrial ni benchmark ciego.

