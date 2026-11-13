# Agente de geometría — demo local

## Identidad y autorización

- Identidad: agente de IA de geometría; no representa a una persona.
- Rol: A, ingesta y geometría determinista.
- Archivo autorizado explícitamente por el usuario en la delegación del 2026-11-13.
- Última actualización: 2026-11-13.

## Tarea de la sesión

- Objetivo: ingesta DXF con `ezdxf` y propuestas deterministas para la demo de una estantería rectangular montada, preservando evidencia, incertidumbre y procedencia.
- Referencia: T1–T3 y soporte honesto de T11 para plano pobre.
- Estado: terminado para integración.

## Alcance y reservas

- Puedo editar: `backend/app/ingesta/`, `backend/app/geometria/`, `backend/tests/test_geometry.py` y este archivo.
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

## Siguiente bloque

- Integrar con fixture público cuando D publique su commit y contrastar el recorrido completo en rama coordinadora.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-13 | Mantener cálculos puros y deterministas; separar observación, derivación e hipótesis | Reglas de arquitectura y trazabilidad | Delegación y documentación del repositorio |
| 2026-11-13 | A acepta contrapropuesta B: extracción sin propuestas; `dimensions.origin=observed|derived`; `warnings` y `synthetic`; hipótesis aparte | Evitar mezclar hechos con interpretación | Mensajes explícitos A/B y aviso posterior a C |

## Dependencias / avisos

- Necesito de B: commit con tipos contractuales 0.2 bajo su ownership.
- Necesito de D: forma pública del fixture sin acceder a la referencia reservada ni codificar sus medidas.
- Afecta a C: IDs, unidades, contornos, cotas, vistas y propuestas que consumirá el visor.
- Aviso realizado: contrato final comunicado a frontend y fixture coordinado con evaluación el 2026-11-13.
- Cambio de `contratos/`: no aplica; A no escribirá contratos.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| Geometría + contrato | `python -m pytest backend/tests/test_geometry.py backend/tests/test_backend_contract.py -q` | 9 passed | Fixture público de D aún no integrado |
| Fixture público | `extract_drawing` sobre ambos `data/planos_demo/*.dxf` | montada: ready/mm, 3 vistas, 3 contornos, 4 cotas; incompleta: ready/mm, 3 vistas, 3 contornos, 3 cotas | La revisión semántica vive en hipótesis/escenario, no en la salud de ingesta |
| Suite completa tras fixture | `python -m pytest -q` | 30 passed | Incluye 8 pruebas de aislamiento/fixture de D |
| Sintaxis/diff | `python -m compileall -q backend/app/ingesta backend/app/geometria`; `git diff --check` | pasa sin salida | No sustituye prueba E2E |

## Bloqueos y cierre

- Bloqueos: ninguno para el alcance propio.
- Pendientes: adaptación B de hipótesis a escenarios en integración.
- Límites: modelspace; subconjunto LINE/LWPOLYLINE recto/TEXT/MTEXT/DIMENSION lineal; sin bloques, arcos, bulges, paperspace ni inferencia de unión física. Los contornos de líneas detectan rectángulos axis-aligned con lados completos.
- Reservas liberadas: ninguna.
