# Private production implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Track evidence per task; the user explicitly requested parallel Sol agents and Astra review.

**Goal:** Deliver the existing table workflow as a testable private-team application with configurable economics and operational safeguards.
**Architecture:** Preserve the deterministic ledger, bounded generative programs and human revision. Add private deployment controls, durable jobs, real catalog inputs and verified exports around the current workflow.
**Tech Stack:** Python/FastAPI/Pydantic/SQLite, JS/Three.js, Docker/Caddy.
**Spec:** docs/superpowers/specs/2026-11-14-private-production-design.md

## Global Constraints
- Read-only audit baseline 10da225 passed 313 Python and 82 JS tests.
- Implementation agents: gpt-6.1-sol; final reviewer: gpt-6-astra.
- No source measurements invented or overwritten, no unknown silently treated as zero.
- One writer for contratos/modelos.py (economics agent B, transferred to PR-replay B after its completion); A/B explicitly agree additive interfaces and notify C before contract edits.
- Offline checks do not call a provider. The user's subsequent explicit authorization covers normal main/PR publication and an isolated deployment through SSH `kripta`; never commit secrets or interfere with existing applications.
- Shared isolated worktree, disjoint ownership, no worker git commits; coordinator integrates and commits inspected files.

## Review Focus
- Parallel revision requests and retries must not corrupt history or duplicate events.
- Real tariffs missing provenance or required quantities cannot become a complete budget.
- Reload or interrupted network must not silently replace a newer result or lose job status.
- Unknown/conflicting CAD and human overrides preserve separate evidence.
- Fresh deployment, restart and backup restore must retain identities/results/artifacts safely.

### Task 1: Private API and persistence (backend)
Files: backend/app/main.py, backend/app/servicios/repository.py, new backend/app/operacion/*, new backend/tests/test_private_*.py, team/agente_backend.md.
- [ ] Reproduce audit findings; tests first for transactional revisions, idempotency, event sequencing and estimates consistency.
- [ ] Implement authenticated private mode using named users and hashed passwords from server config, trustworthy reviewer attribution, bounded request processing and safe errors. Local demo remains compatible.
- [ ] Add durable bounded job endpoints for frontend submission/status with restart handling; preserve existing /runs behavior for integrations.
- [ ] Wire injected economic catalog and new economic scope through existing routes. Coordinate exact interface with task 2.
- [ ] Publish runtime environment and auth/job API to tasks 4/5; run targeted tests.

### Task 2: Economic completion and contract (economics)
Files: contratos/modelos.py (sole writer), estimacion/table_costs.py plus catalog loader, semantic/descriptor.py, related new/existing economic tests, own team/agente_costes_produccion.md.
- [ ] Agree A/B additive delta with geometry; notify frontend/backend before code changes.
- [ ] Support configured real catalog with version/source/date; retain labeled demo catalog. Validate tariff concept/unit/scope.
- [ ] Explicit scope for material, edge, operations, labor hours, finishing and exclusions with human reasons. Add per-component material overrides if coherent with interface.
- [ ] Compute reproducible complete/partial costs, hours, largest contributor and optional provisional sale price from explicit margin; never equate biggest piece with highest cost automatically.
- [ ] Persist catalog snapshot/provenance in estimate. Keep v0.5 payloads readable.
- [ ] Add correction of human-confirmed table values in cooperation with geometry; test conservation of observations.

### Task 3: Geometry, review and derived drawings
Files: geometria/*, ingesta/*, servicios/{decomposition,reconstruction,table_reconstruction}.py, salida/*, geometry tests, team/agente_geometria.md.
- [ ] Fix reproduced audit failures with independent regression values.
- [ ] Ensure repeated review can amend a prior human value; raw observed ledger remains unchanged and contradictions remain blocking.
- [ ] Verify general, component and cut sheets carry all supported length/width/thickness dimensions, occurrence quantities, state and provenance.
- [ ] Improve missing component views/dimensions where supported; do not invent joints/manufacturing claims.
- [ ] Agree contract delta with B; notify frontend; run geometry/render regression checks.

### Task 4: Integrated private-team interface
Files: frontend/*, team/agente_frontend.md.
- [ ] Integrate job submission/polling, session identity and restored state with API from task 1.
- [ ] Show configurable real/demo costs, operation quantities and explicit exclusions/price from task 2.
- [ ] Fix audit issues: missing events/labels, revision-required API methods, stale requests, edit prior human values, keyboard/focus basics.
- [ ] Add meaningful logic tests and actual browser flow evidence, preserving current design.

### Task 5: Deploy, backup and repeatable validation
Files: Dockerfile, compose.yaml, .dockerignore, deploy/*, .github/workflows/*, tools/backup.py, tests/test_backup.py, docs/PRODUCCION.md, own team/agente_operacion.md.
- [ ] Nonroot container with local frontend dependencies, persistent volume, healthcheck, TLS reverse proxy and no public unauthenticated backend port.
- [ ] Deployment configuration matches task 1; documented named-user setup without embedding secrets.
- [ ] SQLite-consistent backup and verified restore to new destination, no destructive overwrite; tests for snapshot integrity and unsafe archives.
- [ ] CI Python/JS and packaging checks; test container if engine available, otherwise explicitly record limitation.

### Task 6: Independent acceptance and audit closure
Files: tools/audit_production.py, tests/test_production_acceptance.py, evaluation/* additions, docs/AUDITORIA_COMPLETA_2026-11-14.md; coordinator owns README/AGENTS/CLAUDE historical status banners.
- [ ] Record complete history/docs/source audit and distinguish old claims from current capabilities.
- [ ] End-to-end offline acceptance for review→drawings→costs→export/restart and negative cases.
- [ ] Regenerate stale evaluation inputs to a new local output, verify no answer leakage; keep external data out of Git.
- [ ] Run full suite, HTTP and browser checks; package actual diff and evidence for Astra.
- [ ] Fix reviewer findings and report observed limits, deployment status and outstanding external acceptance.

### Task 7: Authorized isolated VPS deployment
User identified SSH alias `kripta` and `gex-dashboard.hopto.org` on 2026-11-14, explicitly requiring preservation of every existing site/app.
- [x] Read-only inventory of existing proxy, ports, containers, storage and health; do not read secrets.
- [x] Add base-path support for a dedicated endpoint (`/vexplorer/`) without intercepting existing root/API routes.
- [ ] After acceptance/Astra review, transfer only runtime/config; use the prepared venv and a dedicated user service on free loopback port 18792. Docker is an alternative for new hosts, not this VPS.
- [ ] Add the smallest validated proxy route, with backup of the exact changed configuration and reversible rollback; never stop/recreate existing stacks.
- [ ] Verify TLS/auth and full application at new endpoint; compare existing service health before/after.
- [ ] Record deployed image digest, route, data/backup location and outstanding business-data validation.

### Task 8: PR #1 reviewed integration
User explicitly requests merging PR1 after conflict resolution and adopting improvements. Current head 0fe4be7 (14 commits); baseline blocks 1/2 already selectively adapted. Root preserves current production snapshot, ports useful block3 changes, then records a real merge with both parents and explicit resolutions preserving adapted code.
- [ ] Port bounded union-find and curve/hidden-line/hole evidence improvements; test 25k disconnected lines and deterministic outputs.
- [ ] Distinguish paperspace annotations/dimensions with global limits including nested content; fix reproduced dimension-attachment false pass using actual geometry.
- [ ] Adapt recorded replay to all 3 runners/jobs/auth: DB-authoritative live provenance, exact input/config/transcript checks, no provider calls on replay; preserve human review separation.
- [ ] Add bounded strict candidate comparison to relevant tool sets with current revision validation.
- [ ] Add declared ruff dev extra, preserve main package-data and document decisions for all PR commits.
- [ ] Verify complete integrated tree and fresh Astra review before normal push/merge and VPS rollout. No force push, no raw legacy overwrite.
