# Semantic Evaluation v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make semantic F1 represent complete recovery, publish abstention coverage and split results, and run the wider frozen benchmark with Sol for both phases.

**Architecture:** Keep the evaluator offline and reference-bound by exact prediction bytes. Score required unknown items as unrecovered in the primary metric while retaining an explicitly named covered-only view. Carry reference split through parsing and aggregate each split independently.

**Tech Stack:** Python 3.11+, pytest, existing JSON CLIs.

**Spec:** `docs/EVALUACION_SEMANTICA.md`

## Global Constraints

- Never expose private references or secrets to runtime, provider, public bundles, or reports.
- Freeze prediction bytes before opening the evaluator-only reference.
- Preserve failed cases in denominators.
- Use `gpt-6.1-sol` for proposer and reviewer.
- Do not edit runtime or contracts.
- Do not commit from this shared dirty worktree; root integrates.

## Review Focus

- A batch with one correct item and many unknown required items must not report perfect primary F1.
- A wholly unknown failed case must contribute false negatives and zero coverage.
- Role, occurrence, and relation coverage denominators must remain explicit and additive.
- Development and holdout metrics must be separately visible even when evaluated together.
- Sealing must bind exact prediction bytes, IDs, input hashes, and split-safe private rows.

---

### Task 1: Complete-recovery semantic metrics

**Files:**
- Modify: `tests/test_semantic_evaluation.py`
- Modify: `evaluation/semantic.py`

**Interfaces:**
- Produces: aggregate and per-case `component_roles`, `physical_occurrences`, and `assembly_relations` with full-recovery counts, `coverage_numerator`, `coverage_denominator`, and `covered_only`.

- [ ] Add independent failing tests for partial and total abstention across roles, quantities, and relations.
- [ ] Run focal tests and confirm v1 incorrectly omits unknown reference items from `fn`.
- [ ] Implement full-recovery primary counts and an explicitly conditional `covered_only` metric.
- [ ] Run focal tests green.

### Task 2: Split-visible evaluation and sealing invariants

**Files:**
- Modify: `tests/test_semantic_evaluation.py`
- Modify: `evaluation/semantic.py`
- Create or modify: `tests/test_seal_semantic_reference.py`
- Modify if required: `tools/seal_semantic_reference.py`

**Interfaces:**
- Produces: report `splits` keyed by private split name without copying reference content.
- Consumes: exact frozen prediction SHA and the existing project/structural partition checks.

- [ ] Add a failing test showing mixed development/holdout currently lacks separate metrics.
- [ ] Carry split through parsed cases and reuse the same aggregation routine per split.
- [ ] Add adversarial sealer tests for malformed/duplicate cases and exact byte binding; change sealing only for a demonstrated failure.
- [ ] Run semantic and sealing tests green.

### Task 3: Sol-only runner defaults and benchmark evidence

**Files:**
- Modify: `tests/test_run_general_benchmark.py`
- Modify: `tools/run_general_benchmark.py`
- Modify: `docs/EVALUACION_SEMANTICA.md`
- Modify: `team/agente_semantica_v2_evaluacion.md`

**Interfaces:**
- Produces: CLI defaults proposer/reviewer `gpt-6.1-sol`; frozen baseline/final prediction and public metric reports for the wider corpus.

- [ ] Add a failing parser-behavior test for the reviewer default.
- [ ] Change the reviewer default to `gpt-6.1-sol` and run runner tests green.
- [ ] Freeze current and preserved-original outputs using public inputs only with vision enabled; do not read private references.
- [ ] Seal/evaluate only after both prediction hashes exist; record commands, split sizes, failures, coverage and complete recovery.
- [ ] Run focal and full suites and document limitations without comparing v1 and v2 F1 directly.
