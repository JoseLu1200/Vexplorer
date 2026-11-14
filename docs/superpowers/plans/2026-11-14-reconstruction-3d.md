# Reconstrucción 3D — Implementation Plan

> Ejecutar inline con superpowers:executing-plans, TDD y revisión final. El usuario ya autorizó el diseño y ejecución en conversación.

**Goal:** materializar hipótesis coherentes por piezas y comparar A/B/C/D realmente.
**Architecture:** contratos Pydantic aditivos, motor puro de geometría/render/export, harness acotado, runner público separado de evaluador.
**Tech Stack:** Python, Pydantic, Pillow/NumPy, FastAPI, Three.js existente, Idol SDK fijado.
**Spec:** ../specs/2026-11-14-reconstruction-3d-design.md

## Global Constraints

No referencias privadas en inferencia. No números inferidos etiquetados como observados. No ejecución de código generado. Mantener abstenciones y fallos. No certificación estructural ni económica. No cambios en contratos compartidos ni archivos concurrentes.

## Review Focus

Piezas flotantes/contactos; caja hueca confundida con material; escala desconocida; una vista contada como otra pieza; fallos API y artefactos parciales; referencia filtrada por ruta o metadata; diferencias entre GLB/planos/BOM.

## Task 1: modelo y artefactos

- [x] RED: dimensiones inválidas, IDs repetidos, hipótesis sin motivo, abstención sin piezas; escena/BOM/GLB consistentes; detecta interpenetración y piezas desconectadas.
- [x] Implementar `backend/app/reconstruction3d/{models,geometry,artifacts}.py` y tests.
- [x] GREEN focal y registro.

## Task 2: harness e integración

- [x] RED: solo entradas públicas, timeout/fallo conservados, validación y reparación acotada, resultados provisionales.
- [x] Implementar `service.py`, router aditivo y consumo visor sin alterar BOM confirmada.
- [x] GREEN focal e inspección HTTP/UI.

## Task 3: dataset y cuatro variantes

- [x] Preparar controles y fixtures funcionales; fijar manifiesto antes de inferencia.
- [x] Instalar Idol aislado y pesos con revisiones; probar CUDA sin compilación inicialmente.
- [x] Ejecutar B solo desde entradas; congelar. Ejecutar A/C/D; conservar errores/latencias/memoria.
- [x] Renderizar y revisar visualmente; puntuar con referencias solo en evaluador; probar recuperación/comprensión con cobertura declarada.

## Task 4: verificación y entrega

- [x] Suite pertinente, diff, revisión independiente y correcciones necesarias.
- [x] Informe de resultados reales, galería, limitaciones y procedimiento reproducible.

Cierre y evidencia: `docs/RECONSTRUCCION_3D_REVISION.md`. Limitación de congelación privada inicial documentada; métricas de bordes añadidas en evaluación revisada.
