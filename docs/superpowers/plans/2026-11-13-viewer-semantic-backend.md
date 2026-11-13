# Viewer and Semantic Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pre-run drawing ledger, revision-bound explanations and 3D scenes, plus an auditable local furniture library with deterministic geometric similarity and explicit OpenAI embeddings.

**Architecture:** Extend the frozen Pydantic contract additively so old persisted runs still validate. Keep deterministic descriptor/explanation/similarity services independent from the OpenAI embedding boundary; SQLite stores the latest revision per run and caches validated vectors. FastAPI exposes read-only queries without hidden network calls and explicit POST actions for storage or embeddings.

**Tech Stack:** Python 3.11+, Pydantic 2, FastAPI, SQLite, httpx, pytest.

**Spec:** `docs/SEMANTICA.md`, `docs/CONTRATOS_DATOS.md`, and the 2026-11-13 phase section in `team/agente_coordinador.md`.

## Global Constraints

- B is the sole writer of contracts; A owns extraction/reconstruction implementations.
- No access to `evaluation/reference/**`, no PlankAssembly, no filename/source IDs in canonical descriptors.
- `GET` endpoints never call OpenAI; semantic embeddings are generated only by explicit `POST` actions.
- Geometric scores and cosine scores are separate and cosine is never described as probability.
- Old 0.2 persisted payloads remain readable through additive defaults.

## Review Focus

- Unknown units must null all metric text/graphic points.
- A corrupt, non-finite, zero, wrong-length, or incompatible embedding must be rejected.
- Revisions of the same run must not appear as separate library neighbors or group members.
- Descriptor fingerprints must be stable across IDs, input ordering, filenames, and scene translation.
- An unsupported drawing must remain viewable after run decomposition returns an error.

### Task 1: Additive contract and document drawing endpoint

**Files:** Modify `backend/app/contratos/modelos.py`, `backend/app/main.py`; create/modify `backend/tests/test_backend_contract_viewer.py` and `backend/tests/test_backend_api_viewer.py`.

- [ ] Write contract and pre-run drawing endpoint tests; run them and confirm missing-model/404 failures.
- [ ] Add the agreed 0.3 drawing and scene models with retrocompatible defaults and ledger validation.
- [ ] Persist document extraction independently from runs and expose `GET /api/v1/documents/{document_id}/drawing`.
- [ ] Run focused and complete Python suites, then commit and share the contract hash with A/C/D.

### Task 2: Revision explanations and scene API

**Files:** Create `backend/app/servicios/explanations.py`; modify `backend/app/main.py`, `backend/app/agente/tools.py`, repository and backend tests.

- [ ] Write failing tests for source/formula/unknown explanations, revision listing, scene dispatch and stale revision behavior.
- [ ] Implement deterministic explanation bundles without chain-of-thought and add the public tool schema.
- [ ] Bind explanation/scene responses to exact result revisions and add them to JSON export.
- [ ] Run focused and complete suites, then commit.

### Task 3: Canonical descriptor and offline library

**Files:** Create `backend/app/semantic/descriptor.py`, `backend/app/similarity/service.py`; modify repository/main and backend tests.

- [ ] Write failing invariance, unknown-field, latest-revision and reproducible-group tests.
- [ ] Implement canonical `furniture-v1` descriptor/fingerprint and separately labeled geometric vector/distance.
- [ ] Add SQLite library persistence, explicit save/list/similarity/groups endpoints, same-run exclusion and difference explanations.
- [ ] Run focused and complete suites, then commit.

### Task 4: Explicit OpenAI embeddings boundary

**Files:** Create `backend/app/semantic/embeddings.py`; modify config, repository, main, `.env.example`, and backend tests.

- [ ] Write failing provider-boundary tests for request shape, cache hits, provider errors, corrupt vectors and incompatibility.
- [ ] Implement `POST /v1/embeddings` with `text-embedding-3-small`, `encoding_format=float`, explicit dimensions and bounded timeout.
- [ ] Persist cache metadata keyed by descriptor fingerprint, version, model and dimensions; never silently fall back.
- [ ] Expose availability metadata without secrets, run all tests, and commit.
