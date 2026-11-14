# Cierre QA funcional independiente

## Identidad y autorización

- Identidad: agente de IA `cierre_qa`, delegado por el agente raíz conforme a la solicitud explícita del usuario del 2026-11-14; no representa a una persona.
- Rol: verificación funcional independiente, solo lectura sobre producto.
- Archivo creado por delegación explícita de `/root` el 2026-11-14.

## Tarea de la sesión

- Objetivo: inspeccionar el diff UX/auth e integrar evidencia nueva mediante navegador real y pruebas focales, sin modificar producto.
- Referencia: `docs/superpowers/plans/2026-11-14-poc-closure.md`, bloque Release/Integración.
- Estado: en curso; alcance ampliado por `/root` para corregir dos defectos frontend reproducidos mediante RED/GREEN.

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

## Siguiente bloque

- Añadir regresiones RED, aplicar correcciones mínimas y repetir QA sobre servidor fresco cuando el árbol final quede estable.

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
| Gate frontend final | `npm test --prefix frontend` | 164 pasan, 6 fallan de 170 | `frontend/tests/similarity-ui.test.js` apareció concurrentemente tras la señal de estabilidad; pendiente de integración ajena |
| Diff e integridad | `git diff --check` + `Get-FileHash -Algorithm SHA256 ...` | diff-check pasa; hashes registrados en transferencia | Avisos CRLF informativos |

## Bloqueos y cierre

- Bloqueos: seis pruebas nuevas de similitud/biblioteca no implementadas en `frontend/tests/similarity-ui.test.js`; comunicado a `/root`, fuera del alcance previo hasta nueva indicación.
- Pendientes: repetir `npm test --prefix frontend` después de integrar ese carril; el rerun de servidor/navegador final ya terminó limpio.
