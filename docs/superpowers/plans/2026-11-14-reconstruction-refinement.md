# Reconstruction refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Cerrar el ciclo plano → propuesta → aclaraciones y cotas → nueva propuesta comprobada.

**Architecture:** Extender el módulo aislado reconstruction3d. Reutilizar fuente congelada, trabajos persistentes y proveedor actual; cada revisión tiene nuevo ID y padre inmutable.

**Tech Stack:** Python/Pydantic/FastAPI existentes; JS/HTML y visor existente. Sin dependencias nuevas.

**Spec:** docs/superpowers/specs/2026-11-14-reconstruction-refinement-design.md

## Global Constraints

No modificar contratos compartidos, datos del benchmark ni ramas ajenas. No certificar fabricación ni generar precios. Toda geometría sigue siendo propuesta.

## Review Focus

- Respuesta vacía o pregunta no emitida: 422 sin llamada al proveedor.
- Fuente modificada o contexto ausente: 409, nunca reconsultar un run distinto.
- Revisión encadenada: conservar aclaraciones/cotas previas sin mutar padres.
- Resultado que contradice cotas explícitas: reparar o fallar sin exportación final.
- Nueva abstención/fallo: no dejar 3D/descargas de la versión anterior.

### Task 1: Restricciones y revisiones persistentes

Files: backend/app/reconstruction3d/{models,service,router}.py; tests/test_reconstruction3d_{service,router}.py.

Interfaces: RefinementRequest(answers, intended_use, envelope_mm), reconstruct(..., clarifications, envelope_mm); POST refine → job con parent_job_id, revision y entradas congeladas.

- [x] Escribir y ejecutar pruebas RED de cotas/entradas y revisión inmutable.
- [x] Implementar validación de texto/cotas, feedback y contexto de usuario.
- [x] Implementar persistencia de fuente/contexto, herencia y límites.
- [x] Ejecutar pytest focal y ruff; commit.

### Task 2: Aclaraciones en el visor y cierre

Files: frontend/reconstruction.{html,js,css}; frontend/tests/reconstruction.test.js; documentación y registro propio.

Interfaces: formulario consume missing_information; envía sólo respuestas no vacías y cotas numéricas; muestra procedencia y enlace al padre.

- [x] Prueba RED para serialización y cambio de estado sin datos obsoletos.
- [x] Implementar formulario, historial y limpieza de visor.
- [x] Verificar navegador escritorio/móvil y recorrido pregunta → respuesta → propuesta.
- [x] Ejecutar suites globales y revisión independiente; corregir hallazgos importantes, documentar límites y commit.

## Ajuste solicitado durante ejecución

El usuario señaló el overhaul UX posterior. Se incorporó su snapshot verificable y la herramienta se integra en el shell actual, con tema/foco/historial preservados. No se cambia la fuente ni se publica. Evidencia en docs/RECONSTRUCCION_3D_INCREMENTO.md.
