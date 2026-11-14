# General assembly implementation plan

> Execute with superpowers:subagent-driven-development. User approved the design and all implementation on 2026-11-14, then explicitly requested GPT-6.1 Sol subagents for all work.

**Goal:** Infer and validate per-instance orthogonal panel assembly from drawing evidence and compare all 16 instances against a private reference.

**Architecture:** Strict Pydantic candidate references public geometry; deterministic server derives transforms and validates them. A bounded native tool loop repairs candidates. Revision-scoped persistence supplies the scene; evaluation is separate from inference.

**Tech Stack:** Existing Python/Pydantic/FastAPI/SQLite and JavaScript/three.js, no new agent framework.

**Spec:** ../specs/2026-11-14-general-assembly-design.md (approved by user in this session).

## Global constraints

- Preserve existing dirty work and semantic assembly relations.
- 5 model calls, 180 seconds, 100 instances, 512 contours initially; configurable bounded runtime.
- No free numeric placements or hidden reference input. Metric orthographic rectangular panels only.
- Orthogonal orientation has positive determinant. View reflection belongs to the projection frame.
- Full quantity coverage; no fabricated unknown quantities or thicknesses.
- Every attempt scoped to run/proposal/review/assembly revisions; stale results never replace current scenes.
- Acceptance: 16/16, dimensions and positions <1 mm after ONE proper global alignment, equivalent normals, no unexplained penetration >1 mm.

## Review focus

- Repeated panels sharing a type must remain separate occurrences and cannot reuse a full physical identity.
- Unknown scale or dimensions must abstain, even with a plausible model response.
- Revision races, cancellation, timeout and exhausted repair budgets must retain BOM without showing rejected placements.
- Signed axes must actually rotate meshes; selection must preserve occurrence and type identities.
- Global matching must not hide one moved panel using per-piece alignment or reused reference boxes.

### Task 1: Contract and deterministic geometry

Owner: assembly_core. Files: modelos.py, new general_furniture/assembly.py and test_general_furniture_assembly.py.
- [x] Add strict frames, correspondence, candidate, report and attempt types; additive legacy-compatible scene fields.
- [x] Write and run failing synthetic tests for valid orientations, complete quantities, mismatched projections, missing scale, invalid references, contacts and penetration.
- [x] Implement build_assembly_context and validate_assembly; derive every coordinate from referenced geometry.
- [x] Pass focal tests and review the contract with runtime/frontend consumers.

### Task 2: Runtime and persistence

Owner: assembly_runtime. Files: assembly_live.py, repository.py, router.py, main.py and new tests.
- [x] Test invalid candidate feedback then correction, exhaustion, revision isolation and read-without-spend.
- [x] Implement strict inspect/evaluate/final tools and bounded provider loop.
- [x] Persist attempts, overlay accepted scenes only for exact revisions, integrate durable phase and retry.
- [x] Run tests including existing API/job compatibility.

### Task 3: Viewer

Owner: assembly_viewer. Files: frontend/core/scene.js, components/SceneViewer.js, app.js, api/client.js and tests.
- [x] Test 16 occurrence identities, rotations, selection and legacy fallback.
- [x] Render real transforms; provide separated inspection and explicit hypothesis/status presentation.
- [x] Run frontend suite and browser regression.

### Task 4: Independent evaluation

Owner: assembly_evaluation. Files: evaluation/assembly.py, tools/evaluate_assembly.py, tests/test_assembly_evaluation.py.
- [x] Test global proper rotation/translation and bijective correspondence on asymmetric 16-panel fixtures.
- [x] Test missing/extra/moved/rotated/reflected panels fail and symmetric equivalents pass.
- [x] Emit coverage, center/face error, normalized errors, orientation, penetration and acceptance.

### Task 5: Live integration and review

Owner: coordinator with Sol verification agent.
- [x] Run combined regression and independent code review; fix findings.
- [x] Run plank-030 from public DXF/BOM, freeze output before private scoring.
- [x] Run unused furniture and insufficient-evidence control.
- [x] Final browser diagnostic candidate verification: 16 occurrences, explicit Z-up display, selection/orbit/zoom/explode/exit/reload, no JS/network errors.
- [x] Report reproducible observed results and any remaining failure honestly.

## Observed result

Software implemented and independently reviewed (793 Python / 192 frontend tests passing). The real plank-030 candidate matches all 16 reference instances under one proper global transform, but public validation still rejects 8 unresolved AABB penetrations and one shared contour. Completing implementation/check execution does not imply manufacturing acceptance. Unknown-scale and insufficient-quantity controls abstain. Evidence: docs/VERIFICACION_MONTAJE_GENERAL_2026-11-14.md.
