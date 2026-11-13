# Agente de evaluación — fixture y oráculo

## Identidad y autorización

- Identidad: agente de IA responsable del fixture sintético y la evaluación reproducible de la demo.
- Rol: D, evaluación.
- Archivo autorizado explícitamente por el usuario: `team/agente_evaluacion.md`, 2026-11-13.
- El usuario autoriza decisiones autónomas dentro del ámbito, sin despliegue ni `push`.

## Tarea y alcance

- Estado: en curso.
- Propiedad: `data/planos_demo/`, `evaluation/`, `tools/build_demo_fixture.py`, `tests/test_demo*.py` y este archivo.
- Solo lectura/coordinación: contratos, geometría, backend, frontend y documentación compartida.
- Solapes comprobados: ninguno; la propiedad está registrada en `team/agente_coordinador.md`.

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

## Dependencias / avisos

- B entregará la API vertical para ejecutar el E2E TestClient de revisión, comparable, estimación y exportación.
- La referencia privada nunca se comunica al extractor ni se incorpora a prompts, endpoints, herramientas, índice histórico o runtime.
- No hay cambio de `contratos/` por D.

## Pruebas

| Caso | Comando | Resultado observado | Limitación |
|---|---|---|---|
| TDD rojo | `python -m pytest tests/test_demo_fixture.py tests/test_demo_isolation.py -q` | 7 fallos, 1 pasa antes de generar DXF/manifiesto | Dependencia ezdxf instalada tras declaración de B |
| Fixture e aislamiento reproducible | mismo comando tras generar | 9 pasan; dos procesos generan bytes idénticos | Todavía sin backend integrado |

## Siguiente bloque

- Implementar y ejecutar el E2E independiente contra el backend integrado: salida congelada, revisión versionada, cálculo ligado a revisión, exportación sin duplicar y auditoría dinámica de accesos a referencia.

