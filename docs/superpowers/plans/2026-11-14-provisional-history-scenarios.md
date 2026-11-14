# Provisional Historical Scenarios Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exponer escenarios económicos condicionales y separados para snapshots generales auto-revisados sin promover hipótesis a hechos.

**Architecture:** Nuevos modelos estrictos en `historico.models`, un método de orquestación en `HistoricalStore` que reutiliza retrieval/estimate por comparable individual, y una ruta con callback server-side de snapshot exacto. Integración monta el callback fuera de este cambio.

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, pytest, SQLite.

**Spec:** `docs/superpowers/specs/2026-11-14-provisional-history-scenarios-design.md`

## Global Constraints

- No modificar `main.py` ni `backend/app/contratos/modelos.py`.
- No commits.
- Nunca incluir synthetic ni escribir historial.
- Un escenario por comparable; nunca promediar.
- Snapshot exacto server-side y revisiones obligatorias.

## Review Focus

- Snapshot stale o inexistente produce 404/409, no latest silencioso.
- BOM heterogénea abstiene sin cifras.
- Cantidad/checks/dimensiones insuficientes abstienen por métrica.
- Material/acabado conocidos contradictorios excluyen la referencia; desconocidos quedan como supuesto.
- Moneda/scopes/procedencia se heredan de cada referencia sin mezcla.

---

### Task 1: Contratos y servicio

**Files:**
- Modify: `backend/app/historico/models.py`
- Modify: `backend/app/historico/real_service.py`
- Test: `backend/tests/test_real_history.py`

**Interfaces:**
- Produces: `ProvisionalScenarioSnapshot`, `ProvisionalScenarioRequest`, `ProvisionalScenarioResponse`; `HistoricalStore.provisional_scenarios(snapshot, *, limit, retrieval_method)`.

- [x] Escribir tests RED para escenario individual, ausencia de promedio, supuestos heredados, provenance métrica y abstenciones de evidencia/heterogeneidad.
- [x] Ejecutar los tests focales y confirmar fallo por API ausente.
- [x] Añadir modelos estrictos y servicio mínimo que valida snapshot, agrega BOM provisional, recupera no-synthetic y estima cada comparable por separado.
- [x] Ejecutar tests focales hasta GREEN.

### Task 2: Ruta con snapshot loader

**Files:**
- Modify: `backend/app/api/history.py`
- Test: `backend/tests/test_real_history.py`

**Interfaces:**
- Consumes: `scenario_snapshot_loader(run_id: str, proposal_revision: int, review_revision: int) -> ProvisionalScenarioSnapshot`.
- Produces: `POST /api/v1/history/scenarios` y factory `create_history_router(store, *, max_csv_bytes=..., scenario_snapshot_loader=None)`.

- [x] Escribir tests RED HTTP para carga exacta, envelope, loader ausente, 404 y conflicto de revisión.
- [x] Ejecutar los tests y confirmar fallo por ruta ausente.
- [x] Implementar route y traducción de errores sin aceptar snapshot cliente.
- [x] Ejecutar focal y suite completa; documentar cualquier fallo ajeno.

### Task 3: Documentación y handoff

**Files:**
- Modify: `docs/HISTORICO_REAL.md`
- Modify: `team/agente_historico_real.md`

- [x] Documentar request/response, callback, condiciones y limitaciones.
- [x] Ejecutar `compileall`, `git diff --check` y tests focales.
- [x] Enviar firmas y modelos finales a integración/frontend/Astra.
