# Agente interfaz integral — cierre de brechas de producto

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA frontend integral; no representa a una persona.
- Rol: interfaz web para integrar las brechas de la transcripción en el swarm GPT-6.1 Sol.
- Archivo creado y designado explícitamente: `team/agente_interfaz_integral.md`, delegación del coordinador del 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto: completar el recorrido 2D centrado en `Fuente → Construcción → Por pieza`, con BOM primaria que incluya cotas estimadas aceptadas como aproximadas, láminas acotadas seleccionables y decisiones de impacto comprensibles.
- Referencia del plan: `docs/superpowers/specs/2026-11-14-cad-completion.md`, sobre el worktree aislado `.worktrees/cad-completion` desde `0e65713`.
- Estado: implementación frontend terminada y suite verde; pendiente QA visual HTTP con F01.

## Alcance y reservas

- Archivos o carpetas que puedo editar: `frontend/`, nuevas pruebas frontend y este registro.
- Dependencias que solo leeré: `backend/`, `evaluation/`, documentación y registros de equipo.
- Archivos compartidos que requieren coordinación: contratos y rutas de `backend/app/main.py`; los integra el coordinador/backend, no este agente.
- Solapes detectados y acuerdo para resolverlos: el agente frontend anterior conserva trabajo histórico terminado; la delegación actual asigna a este agente la ampliación integral y exige conservar el diseño vigente. Ningún otro agente actual editará `frontend/`.

## Hecho en el último bloque

- Leídas las reglas, el plan inicial, la transcripción, los registros de equipo y las guías de diseño/TDD aplicables.
- Auditada la superficie actual: el cuaderno técnico ya resuelve plano, revisión especializada, biblioteca y costes; las brechas son de acceso a capacidades nuevas, no de rediseño.
- Baseline frontend ejecutado antes del primer RED: 108 pruebas aprobadas.
- Publicado el plan UI al coordinador y acordadas necesidades de shape con backend general, economía, ingesta e integración.
- Evaluación confirmó que su referencia sigue deliberadamente offline y privada: no se añadirá una superficie de producto ni se expondrá el oráculo.
- Integrados carga y procedencia de DXF/DWG/PDF, selección de página PDF y escala explícita mediante documento hijo inmutable.
- Integrado mueble general con propuesta manual/live versionada, edición replace/split/merge/drop, continuidad explícita de componentes no editados, segunda revisión, cantidad de muebles terminados y moneda ISO separadas de la BOM.
- Expuestos BOM CSV/JSON, descargas SVG/DXF ligadas a propuesta/revisión y esquema SVG dentro del visor técnico existente.
- Integrados importación/listado de histórico real, comparables por atributos y estimación autoritativa de costes/horas con procedencia, fórmulas, incertidumbre y datos ausentes.
- Añadida selección explícita de comparables por atributos o embeddings reales, con modelo/dimensiones visibles, y opt-in sintético desactivado por defecto y propagado a comparables/estimación.
- Añadidos alcances humanos separados de coste/horas, bases actual/cotización/presupuesto/sintética y fechas de fuente visibles sin afirmar actualización temporal.
- Separadas procedencias `actual`, `published` y `synthetic`: una fuente académica publicada se muestra como pública/presupuesto y nunca como ejecución empresarial real.
- Añadidos fixtures JSON generados desde Pydantic para contratos general e histórico; no se mantiene un schema paralelo inventado por frontend.
- Convertido el recorrido general live en un único trabajo durable con propuesta generada y verificación visual automática; la interfaz distingue actor, modelo, política, comprobaciones visuales/deterministas y abstenciones de cualquier corrección humana opcional.
- Separadas incertidumbre, procedencias contribuyentes, alcances y fechas de coste y horas; una fuente que solo aporta presupuesto no se presenta como base de horas.
- Habilitada la página PDF raster como entrada visual de mueble general live sin DXF ni escala: mantiene esas propiedades desconocidas y no habilita por error los recorridos métricos.
- Afinada la semántica de máquina a revisión de coherencia de hipótesis, mostrando si intervino un modelo separado o auto-revisión; no se presenta como confirmación factual.
- Añadidas estimaciones económicas condicionales automáticas por comparable y snapshot exacto: 1 mueble, material/acabado/moneda/alcances de referencia, supuestos, fórmulas, procedencia y coste/horas con incertidumbres separadas; quedan explícitamente fuera de cotización y del histórico confirmado.
- Alineado el CSV BOM local con el artefacto backend: estado de cantidad, estado de ocurrencia, ocurrencias físicas y ocurrencias provisionales de escenario permanecen separadas y visibles.
- Sincronizado el estado vacío con la entrada recomendada y formatos DXF/DWG/PDF; el histórico publicado queda seleccionado inicialmente y resume registros con coste/presupuesto frente a registros con horas.

## Siguiente bloque

- Ejecutar QA visual real sobre F01 en el servidor coordinado, comprobando tabla, cantidad/cotas aproximadas, Construcción, selector Por pieza y descargas SVG/DXF.

## Hecho en CAD completion

- Consumido el contrato Pydantic `package.construction` sin inferir nombres de archivo: summary, piezas, dimensiones/cantidades tipadas, decisiones, sheets y artefactos enlazados por `sheet_id`.
- Convertida la navegación técnica en `Fuente → Construcción → Por pieza`, conservando el visor y diseño existentes.
- La lista primaria muestra valores `estimated+accepted` como `≈`, con rango y estado; valores no aceptados permanecen desconocidos.
- La cantidad estimada también conserva su carácter provisional (`≈ n uds.`), límites, método, explicación y referencias en el inspector.
- Añadidos resumen constructivo y las tres decisiones de mayor impacto ordenadas por el backend.
- Láminas de conjunto y por pieza seleccionables, con descargas SVG/DXF ligadas al snapshot exacto propuesta/revisión.
- CSV local ampliado para conservar estado, rango, método y referencias de cada dimensión.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Integración aditiva sobre el cuaderno técnico existente | Conservar accesibilidad, densidad y recorridos ya verificados sin rediseño innecesario | Delegación del coordinador |
| 2026-11-14 | Datos ausentes, sintéticos o no verificados se muestran como tales | Evitar vender demostraciones como histórico real o completar medidas sin evidencia | Reglas del repositorio y solicitud actual |
| 2026-11-14 | Una estimación aceptada forma parte de la propuesta constructiva primaria y se muestra como `≈`, con rango y fundamento | Dar una salida útil sin promover la estimación a observación ni dejar la BOM vacía | Especificación CAD completion y corrección explícita del coordinador |

## Dependencias / avisos

- Necesito de: contrato final de snapshot constructivo, cotas tipadas, decisiones priorizadas y artefactos SVG/DXF por pieza.
- Afecta a: `frontend/core/general.js`, `frontend/app.js`, `frontend/index.html`, estilos mínimos y pruebas frontend.
- Aviso realizado: coordinación CAD completion iniciada el 2026-11-14 con backend general, ingesta e integración antes de cambios de producto.
- Cambio de `contratos/`: no aplica; este agente solo consume contratos acordados.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Baseline frontend | `cd frontend; npm test` | 108 passed, 0 failed | Sin navegador ni backend nuevo todavía |
| Suite frontend final | `cd frontend; npm test` | 145 passed, 0 failed | DOM cubierto por contratos estáticos y funciones puras; smoke interactivo coordinado aparte |
| Sintaxis de aplicación | `node --check frontend/app.js` | exit 0 | No sustituye el navegador |
| Contratos backend focales | `python -m pytest backend/tests/test_general_furniture_router.py backend/tests/test_general_furniture_review.py backend/tests/test_general_furniture_derivations.py backend/tests/test_integral_api_integration.py backend/tests/test_real_history.py -q` | 45 passed, 0 failed | No ejecuta toda la suite del repositorio |
| Contratos scope/histórico finales | `python -m pytest backend/tests/test_general_furniture_router.py backend/tests/test_general_furniture_review.py backend/tests/test_general_furniture_derivations.py backend/tests/test_real_history.py -q` | 36 passed, 0 failed | Focal tras congelar scopes separados |
| Contratos autónomos finales | `python -m pytest backend/tests/test_general_furniture_autonomous.py backend/tests/test_general_furniture_router.py backend/tests/test_real_history.py -q` | 35 passed, 0 failed | Cruce Pydantic/rutas tras incorporar verificación machine e incertidumbre por métrica |
| Integración HTTP multiformato final | `python -m pytest backend/tests/test_integral_api_integration.py -q` | 11 passed, 0 failed | Incluye PDF raster seleccionado → job visual general → revisión automática |
| Integración HTTP + escenarios económicos | `python -m pytest backend/tests/test_integral_api_integration.py backend/tests/test_real_history.py -q` | 54 passed, 0 failed | Incluye ruta `/history/scenarios`, snapshot exacto y exclusión de sintéticos |
| Frontend CAD completion focal | `node --test tests/general.test.js tests/ui-contract.test.js` | 37 passed, 0 failed | Presenter, estimaciones, cantidad, plan y contrato estático de navegación |
| Suite frontend CAD completion | `npm test` | 159 passed, 0 failed | Pendiente recorrido visual real con F01 |
| Sintaxis CAD completion | `node --check app.js` | exit 0 | No sustituye QA visual |

## Bloqueos y cierre

- Bloqueos: ninguno de frontend; esperando servidor/run coordinado para QA visual F01.
- Pendientes: QA visual del flujo 2D y corrección de cualquier defecto reproducible.
- Reserva activa: solo `frontend/`, pruebas frontend y este registro en `.worktrees/cad-completion`; no se tocará el checkout raíz ni el checkpoint 3D `803faae`.
- Entrega a otra persona: `/root`, sin commit propio, mediante diff explícito del worktree compartido.

## QA visual del commit 208c5d6

- Worktree detached y limpio: `.worktrees/qa-208c5d6`, commit exacto `208c5d677c3c42fac08e682468abd464f4c37e4c`.
- Servidor temporal read-only en `127.0.0.1:8770`: frontend del commit; proxy a `8768` limitado a GET/HEAD y POST de consulta `/api/v1/history/scenarios`.
- Run inspeccionado sin mutaciones: `run-ea59dd9db4244132a6e43aaa020d0e66`.
- Evidencia en `.runtime/qa-208c5d6/`: fuente, esquema general, coste/escenarios, botones BOM e histórico publicado, más `report.json`.
- Resultado: auto-revisión con incógnitas visible; SVG/DXF disponibles; BOM CSV/JSON habilitados; escenarios primero y confirmado plegado; causa geométrica traducida con código; 19 publicados, 4 con coste/presupuesto y 19 con horas; cero errores de consola o red.
- Hallazgo no bloqueante, no corregido durante blind20: al restaurar el run, el badge de procedencia conserva `Fuente pendiente` aunque dibujo y documento están cargados.
