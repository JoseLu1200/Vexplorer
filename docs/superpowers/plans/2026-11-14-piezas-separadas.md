# Piezas separadas Implementation Plan

> **For agentic workers:** usar superpowers:subagent-driven-development o superpowers:executing-plans según la responsabilidad asignada. El swarm paralelo con propiedad aislada fue autorizado expresamente por el usuario.

**Goal:** demostrar DXF de piezas separadas → observaciones → clasificación/montajes hipotéticos → revisión → reconstrucción/descriptor/similares, sin entrada ensamblada.

**Architecture:** contrato Pydantic aditivo 0.4; observaciones de piezas separadas de candidatos de ensamblaje. Rutas de revisión/escena/biblioteca existentes se extienden sin reinterpretar las vistas antiguas.

**Tech Stack:** Python, FastAPI, Pydantic, ezdxf, herramientas nativas y bucle propio, JS/HTML/Three.js local.

**Spec:** [diseño](../specs/2026-11-14-piezas-separadas-design.md); nombres exactos del [contrato A/B](../../CONTRATO_PARTS_ONLY_0_4.md).

## Global Constraints

- DXF de piezas separadas sin montaje completo ni referencia 3D como entrada.
- Pydantic es la única fuente de contratos; B es su único escritor.
- Cantidad no equivale a número de vistas; asociación, magnitudes y cantidades desconocidas se conservan como `null`.
- Ninguna referencia privada del evaluador se carga en el runtime o el prompt.
- Familia, roles y montaje son hipótesis hasta revisión; medidas/cálculos deterministas y trazables.
- Modos y proveedor reales identificados; sin fallback fingido.
- Un responsable por archivo; worktrees desde `dab7ce5`; root integra y prueba.

## Review Focus

1. Un mismo panel en tres vistas: conservar una identidad y cantidad explícita/unknown (A/D).
2. Espesor/quantity ausentes o cotas contradictorias: no inventar sólidos ni familias confirmadas (A/B/D).
3. Permutar keys/orden/trasladar vistas: mantener semántica; variar espesor debe cambiar descriptor (B/D).
4. Solicitudes tardías/revisión antigua: no sustituir la revisión activa ni coste/escena por otra (B/C).
5. Geometría fuera de XY/DIMLFAC: abstenerse o mostrar valor original con conflicto, nunca una cota falsa (A/C).

## Tareas y propiedad

### 1. Contratos y harness/API — B

Archivos: `backend/app/contratos/modelos.py`, `main.py`, `agente/*`, `servicios/repository.py`, servicios de revisión/orquestación nuevos, explicaciones/salida, `semantic/*`, `similarity/*`; pruebas backend de esos módulos. No editar archivos de A.

- [x] Acuerdo A/B escrito antes de implementar; comunicar shapes a C/D.
- [x] Publicar contrato aditivo y pruebas de validación/compatibilidad; commits `86fe0c1` + `6a82a8e`, integrados como `56aeea3` + `700f406`. Asignación de ejemplares por rol en extensión acordada A/B.
- [x] Integrar extracción de A en `POST /runs` explícito; resultados parciales se mantienen revisables.
- [x] Implementar candidatos grounded, revisión y herramientas live sin cifras propuestas por el modelo.
- [x] Derivar descriptor incluyendo espesores y estado de clasificación; versionar espacio semántico y rechazar mezclas incompatibles.
- [x] Probar aislamiento, referencias desconocidas, revisión obsoleta, casos incompletos y exportación ligada a versión; commit de integración.

### 2. Geometría y reconstrucción — A

Archivos: `backend/app/ingesta/dxf_reader.py`, `geometria/extraction.py`, nuevo `geometria/parts.py`, `servicios/reconstruction.py`, sus pruebas. Consume tipos B. No modificar `decomposition.py` legacy para piezas separadas.

- [x] Reproducir OCS/Z/DIMLFAC y corregir con regresiones (commit `854d003`).
- [x] Implementar `extract_separated_parts(extraction)` con keys/vistas/cotas/cantidad evidenciadas y conflictos.
- [x] Implementar `reconstruct_parts_scene(extraction, parts, result)` sin leer montaje de referencia ni fuentes legacy de conjunto.
- [x] Probar varias vistas ≠ cantidad, ejes sin ordenar, unidad desconocida, huecos y posiciones explícitamente hipotéticas; commits.

### 3. Fixtures y aceptación — D

Archivos: `tools/build_parts_fixture.py`, `data/planos_demo/piezas_*`, `evaluation/reference/piezas_*`, `tests/test_parts_only_evaluation.py`.

- [x] Generar solo vistas de paneles, etiquetas opacas y cotas/cantidades admitidas; público `4ae1cee`, referencia privada `7d3376c` solo evaluador/root.
- [x] Variantes con faltantes, asociación ambigua y posiciones/keys/dimensiones distintas; metadatos neutralizados en `1c399af`.
- [x] Prueba de recorrido que congela salida antes de abrir referencia; auditoría de aislamiento y aritmética.
- [x] Ejecutar pruebas relevantes y entregar commits/evidencia a root.

### 4. Visor y revisión — C

Archivos: `frontend/*` y tests JS; consume contrato B.

- [x] Selector explícito de entrada y piezas/vistas asociadas; conservar 2D ante falta de montaje.
- [x] Entidades interiores y encuadre por vista; selección bidireccional exacta por IDs.
- [x] Mostrar familia/rol/montaje como hipótesis, desconocidos y premisas; revisión y escena nueva.
- [x] Bibliotecas y descriptor legible, traza actualizada; comprobar cambios de run/revisión y pantalla estrecha.
- [x] Tests JS y smoke contra API real; commit.

### 5. Integración, aceptación y entrega — coordinador

Archivos: este plan, diseño, `team/agente_coordinador.md`, README/informe nuevo de aceptación; coordinación de cherry-picks/merges.

- [x] Conservar auditoría baseline y evidencia HTTP/browser/live (`59623ef`), reforzada `20540ff` + `0a8161a`; Astra SHIP de auditoría, no de la nueva implementación.
- [x] Integrar contrato y commits en `feat/parts-integration`, resolver solo con el dueño del archivo.
- [x] Ejecutar suites finales y HTTP real; nueva instancia aislada y recorrido en Chrome con DXF de piezas separadas.
- [x] Ejecución live y embedding reales si están configurados; registrar resultados sin secretos.
- [x] GPT-6 Astra revisa diff final/evidencias; SHIP sobre `cbc549a`, con hallazgos corregidos y suite final verificada.
- [x] README con comandos/guion reales, capacidades verificadas y límites; integrado y subido a main en `06cf51e`, remoto sincronizado.
