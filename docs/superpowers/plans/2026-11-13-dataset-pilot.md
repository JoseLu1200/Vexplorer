# Dataset pilot implementation plan

> **For agentic workers:** Use superpowers:executing-plans for this single bounded preparation task; do not implement the application contracts.

**Goal:** Prepare a reproducible development pilot from the downloaded corpus, separating agent inputs and evaluator references.
**Architecture:** An offline Python CLI verifies the source manifest and indexed paths before creating a new output directory. It copies the 14 DXF inputs and creates three raster-only PDF inputs from explicitly recorded crops, with references and provenance outside the agent input tree.
**Tech Stack:** Python 3.11+, PyMuPDF, pytest; dependencies declared in root pyproject.toml for tooling only.
**Spec:** docs/CASO_DE_USO_Y_EVALUACION.md and docs/TEST_PLAN.md. This is preparation of technical development cases, not completion of T11 or a product benchmark.

## Global constraints

- Original corpus unchanged; no API calls, secret reads, download or deployment.
- No new contracts/ models or invented A/B approval.
- User explicitly deferred the personal team file in this session; no fictional identity is created.
- All inspected variants belong to development; no blind-test claim.
- DXF is native and annotated, for extraction only. Derived PDF inputs are raster visual tests and cannot establish native CAD parsing or dimensions from pixels.
- Pass only ONE per-case ZIP to a future evaluator agent, with fresh context; the aggregate input ZIP is for transport only. Separate directories are not an OS security boundary.

## Review focus

1. Corrupted or missing source files: fail before producing a final package.
2. Traversal/absolute paths and unlisted indexed inputs: reject manifest/index references.
3. Existing output or source overlap: refuse without changing source/output.
4. Hidden PDF text, attachments and source metadata: rebuild from cropped pixels in a new document.
5. Reference leakage and quantity confusion: keep evaluator labels out of agent ZIP, retain unknown quantity for isolated detail views.

## Task 1: audited development pack

**Files:** tools/prepare_evaluation.py; tests/test_prepare_evaluation.py; pyproject.toml; docs/PILOTO_DATASET.md; README.md; .gitignore.
**Interfaces:** audit_dataset(source: Path) -> Audit; render_crops(source: Path, destination: Path, crops: tuple[tuple[float,float,float,float], ...]) -> None; prepare_dataset(source: Path, destination: Path) -> Audit. CLI: python -m tools.prepare_evaluation --source PATH --output PATH; --audit-only skips generation.

- [x] Write synthetic tests for clean/corrupt/missing manifests, unsafe paths, missing/unlisted index paths, output overlap/existing output, and raster PDF content isolation. Stub functions raise NotImplementedError; run pytest to observe failure.
- [x] Implement audited source loading and PDF reconstruction, then verify the same tests pass.
- [x] Generate three PDF cases: assembled 2D view only; Jaw Pad two orthographic views with cotas; Jaw Pad front only without thickness view. Record exact crops, source hashes, limitations and reference mapping privately.
- [x] Include the 14 indexed DXF copies with neutral filenames and task extraction, along with evaluator-only publisher sidecars and uncertainty notes. No source scripts are executed.
- [x] Produce one ZIP per case, agent_inputs.zip for transport only, and evaluator_reference.zip containing references/provenance. Verify ZIP hashes and expected entries, reopen PDFs and inspect rendered pages.
- [x] Document actual observed checks and commands, run pytest and git diff --check, obtain a fresh review, commit the tooling and report (review pending at this checkpoint). Keep generated dataset outside Git.

## Execution record

- Baseline: documentation-only main at 6d6229d, no application tests existed.
- Native worktree creation failed because the task cwd is the parent of the Git repo. Git fallback created ../Vexplorer-evaluation on feat/dataset-evaluation.
- Preparation does not use an LLM and does not measure inference quality yet.

- Visual QA found a clipped 25.40 annotation: expanded left crop margin from 85 to 70 PDF points.
- Added per-case ZIPs because a full control and its degraded variant must not share an agent context. Both new archive tests failed first, then implementation followed.
