# Plan de implementación: mesa y planos derivados

Base: main `164356b`. Integración del coordinador: `feat/mounted-table-drawings`. El usuario autorizó trabajo autónomo, swarm GPT-6.1 Sol, contratos A/B y revisión final GPT-6 Astra, con merge/push main. [Diseño](../specs/2026-11-14-mesa-planos-derivados-design.md).

## Propiedad y secuencia

Todos conservan las lecturas obligatorias de AGENTS/CLAUDE/README/planes/team/transcripción y los documentos de arquitectura, contratos, evaluación, PlankAssembly y piloto. Revisan además el diseño y código pertinente actual. Nuevas ramas desde main en worktrees propios; no se pisa código compartido. B es único escritor de Pydantic, API y repositorio.

1. **A + B:** acordar y registrar `docs/CONTRATO_MESA_0_5.md` antes de implementar. B escribe el contrato; A valida geometría/medidas/programa y comunica acuerdo a C, D y los apoyos. Revisar también con Astra los riesgos del contrato.
2. **A geometría:** análisis de vistas montadas y medidas admitidas, evaluación determinista de bindings/reglas, validación de hipótesis, reconstrucción de mesa. Archivos nuevos bajo geometria y servicios de reconstrucción; no tocar modelos ni API.
3. **B backend:** Pydantic, routing nuevo, harness generativo nativo, revisión/persistencia, exportación/endpoints e integración de descriptor/biblioteca. No tocar módulos asignados a apoyos.
4. **C frontend:** selector de entrada, propuestas/medidas/decisiones, planos fuente/general/piezas/despiece, cotas/procedencia, costes, descarga y traza. Todos los archivos frontend.
5. **D evaluación:** generador/fixtures propios y variantes, referencia reservada, pruebas de aceptación y auditoría HTTP. No modificar producto.
6. **Apoyo planos (agente Sol):** módulo nuevo de salida de planos SVG/DXF y pruebas, consumiendo contrato acordado. Propiedad exclusiva del archivo; coordina con A/B.
7. **Apoyo costes (agente Sol):** módulo nuevo de costes de mesa por piezas/conceptos y pruebas, consumiendo contrato acordado. Propiedad exclusiva; coordina con B.
8. **Coordinador:** diseño/plan, integración, navegador, informe/README, revisión Astra y push. Mantiene la versión 0.4 ejecutable desde checkout separado mientras se desarrolla esta ampliación.

## Verificaciones requeridas

- [x] Contrato A/B registrado y comunicado; revisión temprana Astra APPROVE en `6ab6c2e` tras cerrar autoridad, cobertura, estados y dependencia de revisión.
- [x] Fixture permitido de vistas montadas y variante incompleta; commits D `79621eb` y `2bd052d`, referencia fuera del runtime/prompt.
- [x] Geometría, programa generativo validado y baseline etiquetada; números calculados localmente.
- [x] Revisión por campo/componente, recálculo y conservación del historial.
- [x] SVG/DXF general, por piezas y hoja de despiece; dimensiones y procedencias consistentes.
- [x] Coste por pieza/concepto y estados de desconocido; tarifas sintéticas explícitas.
- [x] API, UI, biblioteca/descriptor y exportación integrados.
- [x] Pruebas, ejecución live real, navegador y correcciones.
- [x] README/informe y revisión final Astra: SHIP sobre `5241a86`, 313 Python y 82 JS; API/visión real verificadas.
- [x] Push final a main confirmado en `443e9f1`, tras el checkpoint `23b8e01`; sin despliegue ni datasets externos.
