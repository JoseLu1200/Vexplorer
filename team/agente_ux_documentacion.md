# Agente UX documental — auditoría de intención

## Identidad y autorización

- Identidad: agente de IA de auditoría documental; no representa a una persona.
- Autorización: delegación explícita del coordinador dentro del swarm solicitado el 2026-11-14.
- Rol: contrastar la interfaz con la intención funcional y semántica documentada.

## Alcance

- Solo lectura de producto, contratos, pruebas y registros ajenos.
- Propiedad exclusiva: este registro y `docs/AUDITORIA_UX_DOCUMENTAL_2026-11-14.md`.
- Sin cambios de código, contratos, despliegue, commit o push.

## Trabajo realizado

- Inventariados y abiertos completos 94 Markdown propios, excluyendo `.git`, `node_modules` y vendor. Se leyeron todos los registros de `team/`, incluida la plantilla solo para inventario.
- Leídas de forma prioritaria la transcripción literal, README vigente, especificación UX, contratos 0.1–0.6, recorridos general/mesa/piezas, histórico, evaluación y verificaciones.
- Contrastada la referencia visual acotada de `trace-pay`: `frontend/README.md`, requisitos de consola, tokens y reglas base, sin auditar el producto ajeno completo.
- Comunicados hallazgos tempranos a coordinación, frontend funcional y layout/scroll.
- Publicado el mapa de recorridos, criterios de aceptación, precedencia documental y semánticas no simplificables.

## Estado y límites

- Estado: auditoría documental terminada.
- La lectura documental no sustituye QA de navegador ni demuestra que la UI actual cumpla cada criterio.
- Los contratos Pydantic y payloads observados siguen siendo autoridad sobre nombres exactos; este informe no crea un esquema paralelo.
