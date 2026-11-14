# Cierre QA funcional independiente

## Identidad y autorización

- Identidad: agente de IA `cierre_qa`, delegado por el agente raíz conforme a la solicitud explícita del usuario del 2026-11-14; no representa a una persona.
- Rol: verificación funcional independiente, solo lectura sobre producto.
- Archivo creado por delegación explícita de `/root` el 2026-11-14.

## Tarea de la sesión

- Objetivo: inspeccionar el diff UX/auth e integrar evidencia nueva mediante navegador real y pruebas focales, sin modificar producto.
- Referencia: `docs/superpowers/plans/2026-11-14-poc-closure.md`, bloque Release/Integración.
- Estado: terminado en worktree aislado `feat/poc-closure`; tres correcciones frontend reaplicadas y verificadas.

## Alcance y reservas

- Archivos editables: este registro, artefactos ignorados bajo `.runtime/poc-closure-qa/`, `frontend/app.js`, `frontend/index.html` y pruebas frontend focales (ampliación explícita de `/root`).
- Solo lectura: todo el código, pruebas, fixtures, documentación y cambios de otros agentes.
- Prohibido: commits, push, despliegue, servidor/datos existentes en 8771 y llamadas de inferencia pagadas.
- Solapes: ninguno; los artefactos de ejecución están aislados.

## Hecho en el último bloque

- Leídas las reglas, el plan de cierre y los registros activos de cierre.
- Inspeccionado el estado de trabajo y el diff UX/auth a alto nivel.
- Navegador aislado: DXF, revisión 1→3, biblioteca, costes parciales, exportaciones y responsive 390 comprobados.
- Defectos reproducidos: mensaje de biblioteca obsoleto al completarse la revisión y GET 404 esperables de planos/costes aún no generados.
- Defecto PDF reproducido: la escala se presenta como opcional, pero `required` y la validación incondicional del motivo bloquean preparar una página con escala desconocida.
- El 2026-11-14 `/root` prohibió nuevas escrituras al árbol original y designó exclusivamente `.worktrees/poc-closure`; las tres correcciones se reaplicaron solo aquí.

## Siguiente bloque

- Entregar hashes y evidencia al agente raíz; no tocar el árbol original.

## Dependencias / avisos

- Los defectos se comunicarán a `/root`; este agente no editará producto.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| Auth production explicit-off | `.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_private_auth.py` | 11 pasan | 1 aviso Starlette |
| Frontend tras dos primeras regresiones | `npm test --prefix frontend` | 164 pasan | Ejecutado antes del delta PDF |
| RED/GREEN UX | `node --test frontend/tests/ui-behavior.test.js` | 2 fallos esperados RED; 15 pasan GREEN | Prueba contractual de integración JS |
| RED/GREEN PDF | `node --test frontend/tests/ui-contract.test.js --test-name-pattern="PDF pages"` | 1 fallo esperado RED; 15 pasan GREEN | El filtro de Node enumera los 15 tests del archivo |
| Navegador DXF | Playwright en `127.0.0.1:8784`, datos `.runtime/poc-closure-qa/data` | revisión 1→3/2, biblioteca, coste parcial, export JSON/CSV/traza, plano derivado POST 201 | Sin inferencia pagada |
| Navegador responsive | viewport 390×844 | sin overflow horizontal; navegación desplaza el panel activo | Captura en `.runtime/poc-closure-qa/` |
| Navegador PDF sin escala | fixture propio `no-scale-vector.pdf` | POST 200 sin `mm_per_pdf_point`; conserva desconocido | geometry_only rechaza medir, como se esperaba |
| Navegador PDF escala sin motivo | `mm_per_pdf_point=1`, motivo vacío | bloqueo visible y ningún POST adicional | Correcto |
| RED aislado | `node --test frontend/tests/ui-behavior.test.js`; `node --test frontend/tests/ui-contract.test.js --test-name-pattern="PDF pages"` | 2 + 1 fallos esperados antes de reaplicar | Worktree nuevo |
| GREEN aislado | mismos comandos focales | 15/15 + 15/15 | Worktree nuevo |
| Suite frontend aislada | `npm test --prefix frontend` | 164/164 | Requirió `npm ci --prefix frontend` porque el worktree no traía `node_modules` |
| Auth aislado | Python absoluto de `.venv` original, `pytest -q backend/tests/test_private_auth.py` | 11/11 | 1 aviso Starlette |
| Navegador aislado DXF | Playwright, datos nuevos | 7 trazos, 7 decisiones, revisión 2, biblioteca, subtotal 25 EUR, plano derivado POST 201 | Consola 0 errores; sin GET 404 especulativos |
| Navegador aislado responsive | 390×844 | overflow -15 px; panel Biblioteca arriba y activo | Correcto |
| Navegador aislado PDF | fixture copiado a `.runtime` del worktree | sin escala POST 200; escala 1 sin motivo bloqueada; 1 POST total | Sin llamada pagada |

## Bloqueos y cierre

- Bloqueos: ninguno.
- Pendientes: ninguno en este carril; root integra y ejecuta suite global Python.
