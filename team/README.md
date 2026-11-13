# Equipo de agentes de Vexplorer

Estado: swarm autorizado por el usuario el 2026-11-13 para la primera demo ejecutable. Las identidades siguientes son agentes de IA; no representan personas. Las reglas generales están en [CLAUDE.md](../CLAUDE.md), con la autorización específica de la solicitud del usuario registrada en cada archivo.

| Rol | Registro propio | Propiedad principal |
|---|---|---|
| Coordinador | [agente_coordinador.md](agente_coordinador.md) | Integración, README, documentación de aceptación e índice de equipo |
| A, geometría | [agente_geometria.md](agente_geometria.md) | Ingesta/geometría y pruebas; correcciones del preparador y gate rectangular de descomposición según transferencia explícita |
| B, backend | [agente_backend.md](agente_backend.md) | Contratos Pydantic (único escritor), API, revisión, harness, histórico y estimación |
| C, frontend | [agente_frontend.md](agente_frontend.md) | Frontend JS/HTML y pruebas de interfaz |
| D, evaluación | [agente_evaluacion.md](agente_evaluacion.md) | Fixture propio, referencia reservada y evaluación independiente |

Implementación: GPT-6.1 Sol en cuatro worktrees aislados. Revisión final: GPT-6 Astra, solo lectura; no modifica archivos. El coordinador integra mediante commits en `demo/first-executable` y verifica en la raíz del repositorio. No hay identidades humanas deducidas de Git.

## Acuerdo de contratos

A/B acordaron `0.2.0` antes de implementar, y avisaron a C/D. Los registros propios documentan la aceptación. `DrawingExtraction` conserva evidencia observada; escenarios, premisas y resultados revisados son modelos separados. B mantiene [modelos.py](../backend/app/contratos/modelos.py) como fuente única. Los documentos de contrato `0.1.0` siguen como propuesta histórica del plan amplio, no como contrato ejecutable de la demo.

## Coordinación y verificación

- Cada agente mantiene exclusivamente su registro personal; se leen los registros ajenos para comprobar solapes.
- El coordinador mantiene este índice común y registra las transferencias de propiedad antes de nuevas correcciones.
- A no lee las referencias privadas de evaluación. El runtime recibe únicamente el plano permitido y herramientas acotadas al ledger.
- El fixture propio permite integrar sin depender de PlankAssembly; la adaptación del corpus sigue separada y pendiente.
- [DEMO_IMPLEMENTACION](../docs/DEMO_IMPLEMENTACION.md) recoge alcance y secuencia. [VERIFICACION_DEMO](../docs/VERIFICACION_DEMO.md) distingue pruebas observadas y capacidades pendientes.

La [plantilla]( _TEMPLATE.md) permanece disponible para incorporaciones futuras; no concede autorización ni identidad por sí sola.
