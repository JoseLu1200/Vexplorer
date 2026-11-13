# Agente de geometría — demo local

## Identidad y autorización

- Identidad: agente de IA de geometría; no representa a una persona.
- Rol: A, ingesta y geometría determinista.
- Archivo autorizado explícitamente por el usuario en la delegación del 2026-11-13.
- Última actualización: 2026-11-13.

## Tarea de la sesión

- Objetivo: enriquecer el plano con textos y cotas ancladas y generar una escena 3D determinista, trazable y explícitamente incompleta cuando falten revisión, dimensiones o posiciones.
- Referencia: ampliación autorizada de plano, reconstrucción y similitud del 2026-11-13.
- Estado: implementación 0.3 terminada para integración.

## Alcance y reservas

- Puedo editar: `backend/app/ingesta/`, `backend/app/geometria/`, `backend/tests/test_geometry.py`, `tools/prepare_evaluation.py`, `tests/test_prepare_evaluation.py` y este archivo.
- La ampliación para los dos archivos del preparador fue autorizada explícitamente el 2026-11-13; ningún otro agente los edita durante esta tarea.
- Transferencia puntual autorizada tras revisión Astra: también `backend/app/servicios/decomposition.py` y la prueba nueva `backend/tests/test_decomposition_geometry.py`; B fue informado para no solapar.
- Nueva propiedad de fase: `backend/app/ingesta/`, `backend/app/geometria/`, `backend/app/servicios/decomposition.py`, nuevo `backend/app/servicios/reconstruction.py`, `backend/tests/test_geometry.py`, `backend/tests/test_decomposition_geometry.py`, nuevo `backend/tests/test_reconstruction.py` y este registro.
- Solo leeré: contratos, API, frontend, fixture público de evaluación y documentación.
- `backend/app/contratos/` pertenece exclusivamente al agente B.
- Solapes detectados: ninguno; la interfaz con B debe acordarse antes de implementación contractual.

## Hecho en el último bloque

- Leídas las reglas de coordinación, arquitectura, contratos propuestos, geometría, semántica, TDD y evaluación.
- Registrada identidad y alcance antes de editar código.
- Acuerdo A/B 0.2 cerrado explícitamente: `extract_drawing(path: Path) -> DrawingExtraction` entrega observaciones; las hipótesis viven separadas.
- Avisados C del contrato y D de las restricciones del fixture público.
- Implementado lector real `ezdxf` para LINE, LWPOLYLINE, TEXT/MTEXT y DIMENSION lineal; unidades conocidas se normalizan y las desconocidas se conservan sin mm.
- Implementadas vistas neutrales, contornos trazables, observaciones, evidencias y propuestas rectangulares genéricas con cantidad y espesor desconocidos.
- Verificados ambos DXF públicos de D sin abrir `evaluation/reference/**`: tres vistas y tres contornos; la variante incompleta expone una cota menos, sin completar el dato.
- Endurecida la honestidad: cotas angulares quedan fuera con warning; override textual o escala conflictiva conserva warning y `value_mm=null`; trapecios no producen hipótesis rectangulares; límite de 100.000 entidades se aplica antes del análisis.
- Endurecido el preparador: metadata pública uniforme sin diagnóstico de respuesta, sidecar Bench Vise sujeto a ruta segura/manifiesto/hash y lecturas fuente verificadas contra un snapshot inmutable para detectar TOCTOU.
- Corregido el servicio de descomposición: solo contornos cerrados con cuatro esquinas axis-aligned y evidencia fuente atraviesan el gate de estantería; cajas coherentes de trapecios se abstienen.
- Enriquecida la extracción con textos públicos planos, capas/posiciones, cotas lineales segmentadas y ancladas, unidades explícitas y asociación geométrica de vistas.
- Implementada reconstrucción 3D esquemática por ocurrencia física tras revisión: montaje entre/cubriendo laterales, niveles de balda observados, bbox y evidencia; estados incompletos sin sólidos inventados.
- Endurecida la escena revisada: rechaza roles duplicados, longitudes de tapa/base incoherentes y grosor/profundidad discordantes; el nivel observado se declara como cara inferior de balda.

## Siguiente bloque

- Cerrar acuerdo aditivo A/B sobre dibujo enriquecido y escena; avisar C/D; luego implementar por TDD.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-13 | Mantener cálculos puros y deterministas; separar observación, derivación e hipótesis | Reglas de arquitectura y trazabilidad | Delegación y documentación del repositorio |
| 2026-11-13 | A acepta contrapropuesta B: extracción sin propuestas; `dimensions.origin=observed|derived`; `warnings` y `synthetic`; hipótesis aparte | Evitar mezclar hechos con interpretación | Mensajes explícitos A/B y aviso posterior a C |
| 2026-11-13 | A/B acuerdan adición 0.3: `DrawingText`, `DimensionGraphic`, anclajes source/mm, escena por ocurrencia y `reconstruct_scene(extraction, result)` | Visor legible y 3D trazable sin inventar dimensiones o posiciones | Confirmación explícita de B; B único escritor de contratos; avisos C/D |

## Dependencias / avisos

- Recibido de B: contrato aditivo 0.3 en `351fb63`, integrado como dependencia `13d18e4`; A no modificó modelos.
- Necesito de D: forma pública del fixture sin acceder a la referencia reservada ni codificar sus medidas.
- Afecta a C: IDs, unidades, contornos, cotas, vistas y propuestas que consumirá el visor.
- Aviso realizado: contrato final comunicado a frontend y fixture coordinado con evaluación el 2026-11-13.
- Aviso realizado: contrato aditivo 0.3 comunicado a frontend y evaluación el 2026-11-13.
- Cambio de `contratos/`: acuerdo A/B explícito 0.3; B es único escritor, A solo importa modelos.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| Geometría + contrato | `python -m pytest backend/tests/test_geometry.py backend/tests/test_backend_contract.py -q` | 9 passed | Fixture público de D aún no integrado |
| Fixture público | `extract_drawing` sobre ambos `data/planos_demo/*.dxf` | montada: ready/mm, 3 vistas, 3 contornos, 4 cotas; incompleta: ready/mm, 3 vistas, 3 contornos, 3 cotas | La revisión semántica vive en hipótesis/escenario, no en la salud de ingesta |
| Suite completa tras fixture | `python -m pytest -q` | 30 passed | Incluye 8 pruebas de aislamiento/fixture de D |
| Regresiones de revisión | `python -m pytest backend/tests/test_geometry.py -q` | 10 passed | Angular, texto/escala, trapecio y límite cubiertos |
| Suite final | `python -m pytest -q` | 35 passed | Ejecución fresca tras correcciones |
| Preparador | `python -m pytest tests/test_prepare_evaluation.py -q` | 17 passed | Incluye ZIP público y tamper de bytes/ruta/manifiesto |
| Suite tras preparador | `python -m pytest -q` | 39 passed | Baseline, geometría y demo permanecen verdes |
| Auditoría corpus local | `python -m tools.prepare_evaluation --source ../../../engineering_dataset --audit-only` | 421 archivos, 65 casos, 93 rutas; manifiesto `60b45a…` | Solo auditoría; no se regeneró ni publicó corpus |
| Gate de descomposición | `python -m pytest backend/tests/test_decomposition_geometry.py backend/tests/test_backend_flow.py -q` | 6 passed | Rechaza tres trapecios coherentes y mantiene W/D/H rectangular existente |
| Suite tras gate | `python -m pytest -q` | 50 passed | Incluye backend integrado; creó `.vexplorer-data/` local no versionado |
| Contrato y dibujo 0.3 | `python -m pytest backend/tests/test_geometry.py backend/tests/test_backend_contract.py backend/tests/test_backend_contract_viewer.py -q` | 23 passed | Texto se conserva como dato; el frontend debe usar `textContent` |
| Reconstrucción | `python -m pytest backend/tests/test_reconstruction.py backend/tests/test_geometry.py -q` | 20 passed | Cajas esquemáticas, colisiones no evaluadas |
| Suite fase visor | `python -m pytest -q` | 69 passed | Ejecución fresca antes de commits A |
| Hardening escena | `python -m pytest backend/tests/test_reconstruction.py -q` | 8 passed | Incluye cambio de montaje en revisión 3 e incoherencias de revisión |
| Suite final A | `python -m pytest -q` | 72 passed | Ejecución fresca tras hardening |
| Sintaxis/diff | `python -m compileall -q backend/app/ingesta backend/app/geometria`; `git diff --check` | pasa sin salida | No sustituye prueba E2E |

## Bloqueos y cierre

- Bloqueos: ninguno para el alcance propio.
- Pendientes: B integra endpoint de escena; C consume textos/cotas/escena; D ejecuta aceptación independiente.
- Límites: modelspace; subconjunto LINE/LWPOLYLINE recto/TEXT/MTEXT/DIMENSION lineal sin override/escala conflictivos; sin bloques, arcos, bulges, paperspace ni inferencia de unión física. Escena solo para roles y dos montajes admitidos tras revisión; no trasera, material, mecanizados, colisiones certificadas ni sólidos de fabricación.
- Reservas liberadas: ninguna.
