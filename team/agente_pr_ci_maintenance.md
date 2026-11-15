# Agente PR/CI mantenimiento — coordinación de trabajo

## Identidad y autorización

- Nombre declarado por el usuario: agente PR/CI mantenimiento
- Rol: corrección backend delegada
- Archivo creado o designado explícitamente: delegado por el usuario/coordinador el 2026-11-14
- Última actualización: 2026-11-15

## Tarea de la sesión

- Objetivo concreto: hacer atómico el sellado frente a rotaciones y corregir el total de unidades de lotes con piezas sobredimensionadas.
- Referencia del plan: revisión PR/CI P2
- Estado: terminado

## Alcance y reservas

- Archivos o carpetas que puedo editar: `backend/app/precedentes/mantenimiento.py`, `backend/app/precedentes/espacio.py` si fuese necesario, `backend/app/precedentes/lotes.py`, `backend/tests/test_precedentes_lotes.py`, `backend/tests/test_precedentes_atomic_seal.py` y este registro.
- Dependencias que solo leeré: pruebas y módulos relacionados de precedentes.
- Archivos compartidos que requieren coordinación: ninguno fuera del alcance delegado.
- Solapes detectados y acuerdo para resolverlos: reservas históricas en registros previos; el usuario autorizó expresamente esta integración y sus registros.

## Hecho en el último bloque

- Añadida regresión determinista que rota la referencia en la ventana entre validación y escritura.
- `RegistroEspacio.sellar` lee, valida y escribe dentro de un solo `BEGIN IMMEDIATE`, sin abrir una conexión anidada.
- El lote expone todas las unidades y usa solo las que caben para el presupuesto de nesting.

## Siguiente bloque

- Entregar al coordinador para integración y comprobación global.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Mantener el total de unidades separado del presupuesto de nesting | Las piezas sobredimensionadas cuentan en el lote aunque no consuman trabajo de nesting | tarea delegada |

## Dependencias / avisos

- Necesito de: ninguna dependencia externa.
- Afecta a: sellado de embeddings y respuesta de lotes.
- Aviso realizado: coordinación mediante esta delegación.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| RED enfocado | `..\Vexplorer\.venv\Scripts\python.exe -m pytest -q backend/tests/test_precedentes_lotes.py::test_unidades_incluye_las_piezas_que_no_caben backend/tests/test_precedentes_atomic_seal.py::test_rotacion_entre_validacion_y_escritura_no_deja_sello_obsoleto` | 2 failed por los defectos esperados | antes de producción |
| Suite enfocada final | `..\Vexplorer\.venv\Scripts\python.exe -m pytest -q backend/tests/test_precedentes_lotes.py backend/tests/test_precedentes_atomic_seal.py backend/tests/test_precedentes_mantenimiento.py` | 50 passed, 1 warning deprecado de Starlette | warning ajeno |
| Sintaxis y whitespace | `python -m py_compile ...`; `git diff --check -- ...` | exit 0 | archivos del alcance |
| Suite global | `..\Vexplorer\.venv\Scripts\python.exe -m pytest -q .` | avanzó hasta 84% con fallos ajenos; la sesión de herramienta se perdió antes del resumen | integración concurrente, sin resumen fiable |

## Bloqueos y cierre

- Bloqueos: ninguno dentro del alcance.
- Pendientes: el coordinador debe resolver/diagnosticar los fallos globales ajenos observados durante la integración.
- Reservas liberadas: archivos del alcance, 2026-11-15.
- Entrega a otra persona: coordinador de la integración.
