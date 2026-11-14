# Agente de costes de producción — producto privado

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA B de contratos y economía.
- Rol: B, contrato económico y estimación de costes de producción.
- Archivo creado explícitamente por delegación del usuario del 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto: completar el catálogo configurable, alcance, cálculo reproducible y contrato económico de mesas sin inventar cantidades ni presentar tarifas sintéticas como reales.
- Referencia del plan: Task 2 de `docs/superpowers/plans/2026-11-14-private-production.md`.
- Estado: terminado; contrato/engine congelados y comunicados para integración.

## Alcance y reservas

- Puedo editar exclusivamente: `backend/app/contratos/modelos.py`, `backend/app/estimacion/table_costs.py`, nuevo catálogo económico bajo `backend/app/estimacion/`, `backend/app/semantic/descriptor.py`, pruebas relacionadas de contratos/costes/semántica y este archivo.
- Dependencias que solo leeré: geometría, servicios, API, repositorio y frontend.
- Archivos compartidos que requieren coordinación: `backend/app/contratos/modelos.py` requiere acuerdo A/B y aviso a backend/frontend.
- Solapes detectados y acuerdo para resolverlos: geometría implementa correcciones repetidas; este agente sólo materializa el contrato acordado y sus pruebas contractuales.

## Hecho en el último bloque

- Implementado contrato aditivo 0.6 compatible con payloads 0.5, correcciones humanas identificadas y decisiones de fuente por incidencia estable.
- Implementados catálogo real configurable, snapshot, identidad de estimación, alcance completo, horas, margen/precio provisional y contribuidor calculado.
- Corregido descriptor semántico para no ocultar materiales ausentes y conservar overrides sin afirmar precio.
- Publicadas firmas y shapes exactos a geometría, backend, frontend y aceptación.
- Endurecida completitud real: canto/operaciones sin decisión quedan `unknown|required`; exclusiones contradictorias con tarifas/horas/cantidades se rechazan.

## Siguiente bloque

- Integración del catálogo inyectado y persistencia multi-estimación por backend; aceptación global por coordinador.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Catálogo inválido configurado debe fallar explícitamente | Evitar fallback demo silencioso en producción | Delegación Task 2 y diseño de producto privado |
| 2026-11-14 | Precio provisional usa margen bruto `coste/(1-margen)` y excluye impuestos | Evitar confundir coste, markup, impuestos y valor de mercado | Golden case independiente y revisión Astra |
| 2026-11-14 | `estimate_id` deriva de programa, revisión, snapshot y scope | Permitir varias estimaciones reproducibles sin overwrite | Coordinación backend |

## Dependencias / avisos

- Necesito de: backend, integración del catálogo cargado al startup y persistencia por `estimate_id`.
- Afecta a: backend (`get_table_cost_catalog`, `estimate_table_costs`) y frontend (campos económicos aditivos).
- Aviso realizado: contrato final y firmas enviados a geometría, backend, frontend y aceptación el 2026-11-14.
- Cambio de `contratos/`: acuerdo explícito A/B cerrado antes de editar; C/backend avisados.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Baseline | Python absoluto `-m pytest -q` | 313 passed, 1 warning | Antes de cambios compartidos |
| Economía/contrato/semántica | Python absoluto `-m pytest` sobre 6 archivos afectados | 44 passed in 1.66s | Suite global reservada al coordinador |
| Diff | `git diff --check` sobre archivos propios | pasa sin salida | No sustituye integración global |

## Bloqueos y cierre

- Bloqueos: ninguno dentro del alcance propio.
- Pendientes: integración backend/frontend y suite/aceptación global coordinada.
- Reservas liberadas: ninguna.
- Entrega a otra persona: pendiente publicar firmas y nombres exactos.
