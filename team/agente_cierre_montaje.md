# Agente cierre montaje — salida runtime estructurada

## Identidad y autorización

- Identidad: agente de IA `cierre_montaje`; no representa a una persona.
- Rol: cerrar la salida runtime de relaciones y alternativas de montaje.
- Archivo creado por delegación explícita de `/root` el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: extender aditivamente la propuesta GeneralFurniture 0.6 con relaciones y alternativas incompatibles, preservando incertidumbre y referencias cerradas.
- Referencia: `docs/superpowers/plans/2026-11-14-poc-closure.md`, integración runtime–semántica.
- Estado: terminado y congelado; integración conjunta transferida a `/root`.

## Alcance y reservas

- Propiedad exclusiva: `backend/app/general_furniture/assembly_semantics.py`, `backend/app/general_furniture/proposal.py`, pruebas nuevas relacionadas y este registro.
- Solo lectura: `backend/app/contratos/modelos.py`, `backend/app/general_furniture/live.py`, `backend/app/general_furniture/autonomous.py`, evaluación y corpus.
- `modelos.py` tiene como único escritor a `cierre_abstencion`; `live.py` pertenece a `cierre_pdf`.
- Solapes: ninguno en archivos propios; la propagación ajena se coordina por contrato.

## Hecho en el último bloque

- Obtenido acuerdo A explícito de `cierre_corpus`, acuerdo/implementación B de `cierre_abstencion` y aviso C a `/root`.
- Implementada validación cerrada de `source_refs` de montaje contra ledger/contexto, sin abrir referencias ni consultar oráculos.
- Materialización proposal→draft conserva relaciones y alternativas incompatibles sin crear componentes u ocurrencias.
- Tras el primer smoke funcional (assembly vacío y roles libres), coordinado con `cierre_pdf` un contrato de prompt público: roles canónicos, examen de pares visibles y abstención `assembly_not_identifiable` cuando no haya relación respaldada.
- Se rechazó el guardrail universal multicomponente por forzar pares arbitrarios; no llegó a modificarse producto y sus pruebas transitorias se retiraron.
- El smoke dev v2 produjo relaciones correctas con IDs raw reales del ledger, pero agotó reparaciones porque la gramática solo aceptaba prefijos. En el worktree aislado se admiten aliases raw exclusivamente cuando coinciden con un único namespace autorizado; referencias ausentes o ambiguas se rechazan.
- Replay offline de `proposer-call-2/3/4` contra el DXF público exacto materializó 12, 4 y 1 relaciones respectivamente, sin proveedor ni referencia privada.

## Siguiente bloque

- Ninguno en alcance propio; `/root` ejecutará integración conjunta cuando cierren corpus/semántica.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-14 | Alternativas contienen relaciones sobre el mismo universo de componentes | Evitar sumar hipótesis incompatibles como ocurrencias | Delegación de `/root` y contrato con evaluación |
| 2026-11-14 | No se infieren uniones observadas ni geometría numérica | Conservar abstención honesta | Plan de cierre |
| 2026-11-14 | `source_refs` acepta refs tipadas del ledger o refs exactas del contexto anunciado | Cerrar procedencia y evitar acceso a referencia privada | Acuerdo A/B/C |

## Dependencias / avisos

- Necesito de: acuerdo A de `cierre_corpus`, escritura B de `cierre_abstencion`, aviso C a `/root`.
- Afecta a: adaptador de `cierre_semantica`, prompt/schema de `cierre_pdf` y propagación autónoma de `cierre_abstencion`.
- Aviso realizado: contrato final enviado a `cierre_semantica`, `cierre_pdf`, `cierre_abstencion` y `/root`.
- Cambio de `contratos/`: A (`cierre_corpus`) aprobado, B (`cierre_abstencion`) implementó como único escritor y C (`/root`) avisado.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| RED | `python -m pytest -q backend/tests/test_general_furniture_assembly_semantics.py` | 3 failed, 1 passed | Fallos esperados: no propagaba ni validaba refs |
| GREEN | `python -m pytest -q backend/tests/test_general_furniture_assembly_semantics.py` | 4 passed | Fixtures públicos propios |
| Regresión focal | `python -m pytest -q backend/tests/test_general_furniture_proposal.py backend/tests/test_general_furniture_repository.py backend/tests/test_general_furniture_router.py backend/tests/test_general_furniture_assembly_semantics.py` | 13 passed | No sustituye suite completa |
| Lint focal | `python -m ruff check backend/app/general_furniture/assembly_semantics.py backend/app/general_furniture/proposal.py backend/tests/test_general_furniture_assembly_semantics.py` | All checks passed | Solo archivos propios |
| Integración montaje/autonomía | `python -m pytest -q backend/tests/test_general_furniture_assembly_semantics.py backend/tests/test_general_furniture_autonomous.py` | 28 passed | Incluye repair/final effective output |
| Prompt funcional | `python -m pytest -q backend/tests/test_general_furniture_live.py backend/tests/test_general_furniture_assembly_semantics.py backend/tests/test_general_furniture_autonomous.py` | 37 passed | Contrato system/tool/context sin llamada pagada |
| Alias/replay integrado | `python -m pytest -q backend/tests/test_general_furniture_assembly_semantics.py backend/tests/test_general_furniture_live.py backend/tests/test_agent_runtime.py` | 29 passed | Worktree aislado; raw exacto único aceptado, ambiguo rechazado |
| Suite completa | `python -m pytest -q` | 2 errores de colección | Frentes concurrentes: faltaban temporalmente `tools.seal_semantic_reference` y `freeze_paired_semantic_outputs`; raíz ordenó no repetir |

## Bloqueos y cierre

- Bloqueos: ninguno en alcance propio.
- Pendientes: suite completa, benchmark y revisión conjunta pertenecen a `/root`.
- Reservas liberadas: `assembly_semantics.py`, `proposal.py` y prueba propia congelados el 2026-11-14.
- Entrega: contrato, implementación y evidencia comunicados a `/root`; `cierre_pdf` y `cierre_semantica` recibieron nombres finales.
