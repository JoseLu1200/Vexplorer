# Agente assembly core — contrato y geometría determinista

## Identidad y autorización

- Nombre declarado por delegación: agente de IA `assembly_core`; no representa a una persona.
- Rol: único escritor del contrato aditivo de montaje y del validador geométrico.
- Archivo creado por delegación explícita de `/root` el 2026-11-14, bajo la autorización integral del usuario.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: modelar marcos ortográficos, orientación discreta por ocurrencia y correspondencias respaldadas por evidencia; calcular y validar colocaciones sin aceptar coordenadas libres del modelo.
- Referencia: `docs/superpowers/specs/2026-11-14-general-assembly-design.md`.
- Estado: contrato y geometría entregados; disponible para depurar el candidato público real con runtime/QA.

## Alcance y reservas

- Propiedad exclusiva: `backend/app/contratos/modelos.py`, nuevo `backend/app/general_furniture/assembly.py`, nuevo `backend/tests/test_general_furniture_assembly.py` y este registro.
- Solo lectura: runtime, persistencia/API, visor, evaluación, inferencia existente y referencias privadas.
- Solapes: `modelos.py` contiene cambios locales previos que se preservan; `/root` designó a `assembly_core` como único escritor contractual de este incremento. Las reservas históricas constan cerradas o son desplazadas expresamente para este delta.

## Hecho en el último bloque

- Implementados contratos estrictos de marco, orientación, correspondencia, candidato, contexto, informe, intento persistido y estado con alternativas aceptadas.
- Implementado contexto y validador deterministas: escala, cantidades, identidad, evidencia por ocurrencia, mano derecha, contorno/caja, reproyección, dimensiones rotadas, extensión global y penetración.
- Escena ampliada aditivamente con ocurrencia, orientación, tamaño mundial y estados de hipótesis montada, preservando escenas antiguas.
- Fijado y comunicado `position_mm` como mínimo de AABB mundial; el centro de render es `min + size_mm / 2`.
- Auditado el DXF público plank-030: 40/40 contornos y 240/240 medidas métricas, tres regiones heurísticas dentro de una vista de ledger.
- Corregido el gate real: dimensiones/cantidades numéricas en estado `hypothesis` se admiten solo con procedencia y referencias válidas al ledger; las 16 `scenario_occurrences` revisadas se conservan como identidades provisionales. Comprobado directamente con DXF público y revisión persistida.
- Revalidado el candidato público rev4: conserva 16 colocaciones, elimina falsos residuos numéricos y ruido duplicado, y permanece honestamente rechazado por ocho penetraciones AABB de ~5 mm y un contorno compartido sin hipótesis de oclusión.
- Congelado un artefacto separado de revalidación pública con SHA-256, sin modificar el freeze original ni consultar referencia privada.
- Confirmado que plank-016 es un control de abstención correcto: faltan ocurrencias acotadas para `shelf` y `rail_a` por ambigüedades públicas de segmentación/identidad.

## Siguiente bloque

- Ayudar a runtime/QA a reparar con evidencia pública cualquier candidato real rechazado; no consultar referencia privada.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo |
|---|---|---|---|
| 2026-11-14 | La propuesta no contiene posiciones numéricas | Toda coordenada debe derivarse del ledger | Especificación aprobada y delegación `/root` |
| 2026-11-14 | `position_mm` es el mínimo mundial de la AABB | Compatibilidad con el visor existente | Aclaración explícita de `/root` |
| 2026-11-14 | Orientaciones limitadas a permutaciones con signo y determinante +1 | Preservar mano y evitar rotaciones/reflexiones libres | Especificación aprobada |
| 2026-11-14 | Un único marco coherente por región | Evitar alineaciones/reflexiones distintas por ocurrencia | Revisión adversarial de `assembly_review` |
| 2026-11-14 | Alcance inicial solo para componentes `panel` | No encajonar hardware/miembros/desconocidos fuera del alcance aprobado | Especificación y revisión independiente |
| 2026-11-14 | Estado público conserva todas las alternativas aceptadas y marca ambigüedad | No seleccionar silenciosamente la primera solución compatible | Coordinación con runtime |
| 2026-11-14 | Una hipótesis métrica revisada puede montar ocurrencias provisionales solo si enlaza procedencia pública válida | Montaje validado sigue siendo hipótesis, no confirmación de fabricación; evita bloquear la BOM real sin aceptar números libres | Rev3 pública, `/root` y live QA |
| 2026-11-14 | Un solape proyectado con mecanizado no verificado no elimina un error de penetración | Referencias genéricas de contorno no demuestran ranura/rebaje ni geometría mecanizada libre de colisión | Ruling de `/root` y revisión independiente |
| 2026-11-14 | Tolerancia de ajuste de caja 0,01 mm separada de epsilon numérico, reproyección, dimensiones y penetración | Evitar clasificar como no rectángulos residuos flotantes de 1e-5 mm | Revalidación pública rev4 |

## Dependencias / avisos

- Necesito de: runtime para persistir intentos y controlar el bucle; visor para aplicar orientación; evaluación para medir contra referencia separada.
- Afecta a: `assembly_live.py`, repositorio/router, frontend y evaluador.
- Aviso contractual: borrador de nombres/campos enviado a `/root`, `assembly_runtime`, `assembly_viewer` y `assembly_evaluation`.
- Cambio de `contratos/`: autorizado por el usuario y delegado a este escritor exclusivo; consumidores avisados.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| RED inicial | `.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_general_furniture_assembly.py` | 8 fallos esperados por modelos/módulo ausentes | Antes de implementar |
| RED escena estricta | prueba focal `test_placed_scene_item_requires_complete_instance_transform` | 1 fallo esperado: aceptaba transformación parcial | Corregido en contrato |
| RED alcance panel | prueba focal `test_context_abstains_from_unsupported_non_panel_components` | 1 fallo esperado: aceptaba hardware | Corregido en contexto |
| GREEN focal final | `.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_general_furniture_assembly.py` | 22 passed | Incluye hipótesis métrica probada, ruido rectangular y no-waiver de penetración |
| Preflight público real | `build_assembly_context(extract_drawing(plank-030.dxf), persisted_review)` | 10 componentes, 16 ocurrencias provisionales, 3 regiones, 40 contornos | Solo entradas públicas; sin referencia privada |
| Revalidación rev4 pública | `validate_assembly(public_extraction, persisted_review, frozen_candidate)` | rejected; 16 placements; 8 `aabb_penetration`; 1 `shared_contour_identity`; máximo 4,999943339 mm | Artefacto `plank-030-r4-core-revalidation.json`; SHA-256 `b4cc6fa7...731c48` |
| Integración core/runtime final | pytest assembly core/live/repository/router | 44 passed, 1 warning deprecación Starlette/httpx ajeno | Después del contrato de estado/solape y gates públicos |
| Regresión mueble general | assembly/review/derivations/proyecciones/contexto | 36 passed | Antes de las últimas dos adiciones contractuales, luego cubiertas focalmente |
| Suite completa | `.venv\\Scripts\\python.exe -m pytest -q` | 768 passed, 2 warnings deprecación ajenos | 135,21 s; antes de `GeneralAssemblyState` y gate panel, ambos verificados focalmente |
| Lint focal final | `python -m ruff check backend/app/contratos/modelos.py backend/app/general_furniture/assembly.py backend/tests/test_general_furniture_assembly.py` | All checks passed | `modelos.py` contiene cambios previos preservados |

## Bloqueos y cierre

- Bloqueos: la evidencia pública no contiene geometría mecanizada que demuestre holgura para las ocho penetraciones AABB; no se autoriza inventar ranuras/rebajes.
- Pendientes: persistencia/API/visor y presentación diagnóstica por sus propietarios; el candidato rev4 no puede publicarse como montaje validado.
- Reservas liberadas: archivos propios entregados a `/root`; permanecer disponible solo para auditoría final coordinada.
