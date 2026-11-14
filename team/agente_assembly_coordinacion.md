# Assembly implementation coordination

- Identity: AI coordinator for this session, not an inferred human identity.
- Authorization: user approved general-assembly design and explicitly authorized all implementation, then requested GPT-6.1 Sol subagents for all work.
- Scope: integration coordination, plan, local verification artifacts and final report. Contract sole writer: assembly_core. Runtime: assembly_runtime. Frontend: assembly_viewer. Independent evaluator: assembly_evaluation.
- Existing changes preserved. Semantic assembly agent's reserved module/tests are released and remain untouched by this increment. Prior inference and viewer changes are extended additively.
- Ruling: continue on existing feature checkout to preserve uncommitted integrated state; no reset, clean, stash or shared-branch publication.
- Ruling: direct current authorization covers required contract extension and team records; no invented historical A/B approval is claimed. Runtime and frontend are notified through task assignments and interface coordination.
- Plan: docs/superpowers/plans/2026-11-14-general-assembly.md.
- Status: implementation underway; no live assembly success claimed.

## Interface coordination

| Tasks | Shared interface | Resolution |
|---|---|---|
| Core/runtime | Pydantic candidate/report/attempt and pure validator | Core sole model writer; runtime requests additions directly. |
| Core/viewer/evaluator | Position and signed local axes | World AABB minimum for position_mm; world extent separately; local dimensions preserved. |
| Runtime/viewer/live QA | Retry and reads | Explicit durable POST /general/assembly/retry with exact revisions; standard jobs polling. GET cannot spend. |
| Evaluation/live QA | Reference isolation | Live QA freezes output/hash first; evaluator alone reads reference after freeze. |
| Core | Geometry tests vs implementation | Independent synthetic expectations, missing scale abstains. |
| Runtime | Budget vs persistence | Every attempted candidate retained; rejected scene never overlays BOM. |
| Viewer | Legacy vs mounted | Existing schematic fallback retained, explicit mounted hypothesis. |
| Evaluator | Alignment vs matching | One global proper orthogonal transform, bijective instance assignment. |
| Integration | Existing queue vs design assumption | Existing executor has no cancellation endpoint; require honest limitation or tested addition, do not claim it already exists. |

## Observed baseline

- Backend contract/derivations/repository/router/autonomous/live: 60 passed (2.68s), one existing Starlette/httpx deprecation warning.
- Frontend npm test: 175 passed, zero failures.
- Browser existing plank-030 restores 10 component types / 16 quantity sum and legacy schematic; Chrome DevTools page 2 handed exclusively to browser QA.

## Integration verification in progress

- Root full pytest after initial integration: 770 passed, 2 existing deprecation warnings, 146.04s. This predates subsequent runtime fixes and is not the final acceptance evidence.
- First real assembly attempt: provider HTTP400 invalid_function_parameters. Cause: missing recursive strictification of generated tool schemas. Fixed by runtime with regression.
- Second real attempt: model call budget exhausted, no candidate. Frozen failure retained. Root code inspection identified strict Python tuple validation of decoded JSON lists, missing expected assembly revision in context, and omission of the core assembly geometry context. Runtime tasked with fixing all three before another paid run.
- Browser QA: legacy table orbit/zoom/explode/reload and selection pass; incomplete assembly leaves BOM accessible and explicitly says no accepted placements. No mounted success claimed yet.

## Final technical verification

- Root full suite: 793 passed, 2 existing deprecation warnings, 138.82s. Frontend: 192 passed, zero failures.
- Independent Sol review: no residual Critical/Important must-fix. Final terminal diagnostic delta also covered by runtime focal 45 passing tests.
- Production-local service restarted with final backend at https://localhost:8765, launcher PID 13172. No public deployment or commit created; prior dirty work preserved.
- Reference evaluation: all 16 placements match dimensions, centers, faces and normal axes within 1mm after one global proper alignment and bijection. Frozen data and report hashes are recorded in docs/VERIFICACION_MONTAJE_GENERAL_2026-11-14.md.
- Ruling: private-reference agreement cannot waive collisions in public validation. Eight ~5mm AABB penetrations and one shared contour remain unresolved; runtime stays rejected. Unverified machining explanations never bypass that rule.
- Ruling: allow explicit diagnostic inspection of deterministic rejected placements, clearly labelled and never used as an accepted derived scene; default/reload remain schematic. This lets the user inspect actual geometry without implying approval.
- Final public revalidation preserves 16 placements and 9 real issues; numerical box-fit noise and duplicate issue spam corrected.
- Second furniture abstains because occurrence coverage is insufficient; unknown-unit control abstains with assembly_metric_scale_required and zero model calls. No missing quantities or scale invented.
- Final browser verified: explicit diagnostic shows 16 occurrences upright via global Z-up display; selection, orbit, zoom, explode and restore, exit and reload pass. Screenshot: .runtime/assembly-verification/browser-complex-rejected-16-world.png. No JavaScript/network errors. All model work stopped; no further paid calls needed to confirm missing machining evidence. Minor presentation limit: selector visually retains Z immediately after leaving diagnostic, while the scene resets; reload resets selector Y.
