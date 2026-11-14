# Equipo de agentes de Vexplorer

## Correcciones de auditoría — swarm autorizado

El usuario autorizó explícitamente todo el alcance y los registros del swarm el 2026-11-14. Se trabaja en el checkout `data/offline-pipeline-demo`, base `b2bc33d`, conservando otros worktrees. El [plan de hallazgos](../docs/superpowers/plans/2026-11-14-hallazgos.md) y [registro de coordinación](agente_hallazgos_coordinacion.md) delimitan las reservas actuales: `agente_hallazgos_security`, `jobs`, `embeddings`, `frontend`, `browser_ci`, `evaluation` y `review`. Implementadores GPT-6.1 Sol; revisión GPT-6 Astra. Las secciones compartidas de API y persistencia se coordinan explícitamente. La autorización incluye la migración semántica de metadata y sus consumidores; la biblioteca publicada sigue siendo catálogo compartido, sin conceder acceso al proyecto fuente privado.

## Prioridad vigente: completar planos CAD 2D

El usuario corrigió el alcance el 2026-11-14: interpretar vistas de un mueble completo con cotas escasas, deducir o estimar medidas y detalles, proponer piezas necesarias y entregar sus planos acotados con explicaciones útiles. El [diseño vigente](../docs/superpowers/specs/2026-11-14-cad-completion.md) y su [plan](../docs/superpowers/plans/2026-11-14-cad-completion.md) se implementan en `.worktrees/cad-completion`, rama `feat/cad-completion`, base `0e65713`. Las estimaciones numéricas justificadas forman parte del resultado provisional principal y no sustituyen observaciones. No se requiere revisión humana.

Se mantienen los registros personales del incremento integral. Mueble general escribe contratos, inferencia, harness y derivados; histórico real se reasigna al validador de coherencia constructiva; ingesta a planos 2D por pieza; integración a API y persistencia; interfaz al recorrido 2D; evaluación a tres controles propios; coordinación a integración, comprobación visual y commits. Astra revisa en lectura. Se aparcan las ampliaciones de histórico, PDF, 3D y despliegue. Los cambios de la otra sesión UX en el checkout raíz se conservan intactos.

## Ampliación de la transcripción — sesión actual

El usuario renueva el swarm GPT-6.1 Sol con GPT-6 Astra como revisor. Base `4209510`, rama `feat/transcript-completion`. Los registros históricos siguientes conservan su contexto; para este incremento la propiedad activa pasa a los registros nuevos: [coordinación](agente_coordinacion_integral.md), [ingesta](agente_ingesta_general.md), [mueble general](agente_mueble_general.md), [histórico](agente_historico_real.md), [evaluación](agente_evaluacion_integral.md), [interfaz](agente_interfaz_integral.md), [integración](agente_integracion_integral.md) , [operación](agente_operacion_integral.md) , [fuentes públicas](agente_fuentes_datos.md) y [asociación de proyecciones](agente_proyecciones.md). Cada agente mantiene solo su registro. Los contratos tienen un único escritor, mueble general, tras acuerdo con ingesta y aviso a interfaz/integración. El [plan](../docs/superpowers/plans/2026-11-14-transcript-completion.md) documenta tareas y comprobaciones; su existencia no acredita su terminación.

Estado: swarm autorizado por el usuario el 2026-11-13 para la primera demo ejecutable. Las identidades siguientes son agentes de IA; no representan personas. Las reglas generales están en [CLAUDE.md](../CLAUDE.md), con la autorización específica de la solicitud del usuario registrada en cada archivo.

| Rol | Registro propio | Propiedad principal |
|---|---|---|
| Coordinador | [agente_coordinador.md](agente_coordinador.md) | Integración, README, documentación de aceptación e índice de equipo |
| A, geometría | [agente_geometria.md](agente_geometria.md) | Ingesta/geometría y pruebas; correcciones del preparador y gate rectangular de descomposición según transferencia explícita |
| B, backend | [agente_backend.md](agente_backend.md) | Contratos Pydantic (único escritor), API, revisión, harness, histórico y estimación |
| C, frontend | [agente_frontend.md](agente_frontend.md) | Frontend JS/HTML y pruebas de interfaz |
| D, evaluación | [agente_evaluacion.md](agente_evaluacion.md) | Fixture propio, referencia reservada y evaluación independiente |

Implementación: GPT-6.1 Sol en cuatro worktrees aislados. Revisión final: GPT-6 Astra, solo lectura. La primera demo se integró en `demo/first-executable`; la ampliación del visor en `demo/drawing-workbench`. El usuario autorizó después fusionar y subir todo a `main`. El coordinador verifica en la raíz. No hay identidades humanas deducidas de Git.

## Acuerdo de contratos

A/B acordaron `0.2.0` antes de implementar, y avisaron a C/D. Los registros propios documentan la aceptación. `DrawingExtraction` conserva evidencia observada; escenarios, premisas y resultados revisados son modelos separados. B mantiene [modelos.py](../backend/app/contratos/modelos.py) como fuente única. Los documentos de contrato `0.1.0` siguen como propuesta histórica del plan amplio, no como contrato ejecutable de la demo.

La ampliación aditiva 0.3 fue acordada de nuevo por A/B y comunicada a C/D: dibujo enriquecido, escena, explicaciones y biblioteca semántica. A mantiene reconstrucción y B contrato/API. El coordinador implementó el render SVG independiente por transferencia explícita. Los resultados antiguos 0.2 conservan lectura.

## Coordinación y verificación

- Cada agente mantiene exclusivamente su registro personal; se leen los registros ajenos para comprobar solapes.
- El coordinador mantiene este índice común y registra las transferencias de propiedad antes de nuevas correcciones.
- A no lee las referencias privadas de evaluación. El runtime recibe únicamente el plano permitido y herramientas acotadas al ledger.
- El fixture propio permite integrar sin depender de PlankAssembly; la adaptación del corpus sigue separada y pendiente.
- [DEMO_IMPLEMENTACION](../docs/DEMO_IMPLEMENTACION.md) recoge alcance y secuencia. [VERIFICACION_DEMO](../docs/VERIFICACION_DEMO.md) distingue pruebas observadas y capacidades pendientes.

La [plantilla](_TEMPLATE.md) permanece disponible para incorporaciones futuras; no concede autorización ni identidad por sí sola.

## Incremento privado y PR1

El usuario renovó la autorización del swarm GPT-6.1 Sol y revisión GPT-6 Astra el 2026-11-14. La integración actual utiliza la rama aislada `feat/private-production`, con propiedad de archivos disjunta y commits centralizados por el coordinador. Los registros adicionales son [economía](agente_costes_produccion.md), [operaciones](agente_operacion.md), [integración CAD de PR1](agente_integracion_pr1.md) y [replay de PR1](agente_replay_pr1.md). El escritor contractual pasó de economía a replay tras cerrar el primer bloque y acordar el delta con A.

El destino autorizado es un servicio nuevo bajo `https://gex-dashboard.hopto.org/vexplorer/`, mediante `ssh kripta`. La revisión final y la verificación del despliegue deben registrar resultados observados; las aceptaciones anteriores no aprueban automáticamente este incremento.
