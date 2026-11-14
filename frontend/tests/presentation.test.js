import test from "node:test";
import assert from "node:assert/strict";

import { availableModes, componentsForSnapshot, executionModeLabel, fieldOrigin, normaliseRunPayload, presentEstimate, presentReplaySource, snapshotStatusPresentation } from "../core/presentation.js";

test("geometry only stays available while unconfigured provider modes stay disabled", () => {
  assert.deepEqual(availableModes({ live_available: false, replay_available: false }), [
    { id: "geometry_only", enabled: true },
    { id: "live", enabled: false },
    { id: "recorded_replay", enabled: false },
  ]);
});

test("canonical replay capability enables replay without renaming backend fields", () => {
  assert.equal(availableModes({ recorded_replay_available: true })[2].enabled, true);
});

test("run plus result API payload becomes one frontend snapshot", () => {
  const estimate = { result_revision: 1, total: 125 };
  const snapshot = normaliseRunPayload({ run: { id: "run-1", state: "needs_review" }, result: { result_revision: 1, state: "needs_review", pieces: [] }, estimate });
  assert.equal(snapshot.id, "run-1");
  assert.equal(snapshot.state, "needs_review");
  assert.equal(snapshot.result_revision, 1);
  assert.equal(snapshot.result.state, "needs_review");
  assert.equal(snapshot.estimate, estimate);
});

test("estimate presentation preserves unknown rates and backend totals", () => {
  const presented = presentEstimate({
    provisional: true,
    currency: "EUR",
    result_revision: 2,
    line_items: [
      { id: "material", label: "Tablero", quantity: 3.2, unit: "m²", rate: 28.5, amount: 91.2, origin: "calculated" },
      { id: "finish", label: "Acabado", quantity: null, unit: "h", rate: null, amount: null, origin: "hypothesis" },
    ],
    total: 91.2,
  });
  assert.equal(presented.totalLabel, "91,20\u00a0€");
  assert.equal(presented.items[1].rateLabel, "Desconocido");
  assert.equal(presented.revisionLabel, "Revisión 2");
});

test("canonical cost concepts expose their factors and hours without client recalculation", () => {
  const presented = presentEstimate({
    result_revision: 4,
    concepts: [{ id: "material", label: "Tablero", base_amount: 80, factor: 1.14, amount: 91.2, explanation: "Ajuste por superficie", comparable_id: "hist-1" }],
    total: 91.2,
    hours: 7.5,
  });
  assert.equal(presented.items[0].quantityLabel, "Factor 1,14");
  assert.equal(presented.items[0].rateLabel, "Base 80,00\u00a0€");
  assert.equal(presented.hoursLabel, "7,5 h");
});

test("economic factors keep enough precision to explain the backend amount", () => {
  const presented = presentEstimate({ concepts: [{ factor: 1.464, base_amount: 60, amount: 87.84, explanation: "Tarifa sintética 28.50 EUR/m²" }], assumptions: ["Tarifas sintéticas"] });
  assert.equal(presented.items[0].quantityLabel, "Factor 1,464");
  assert.equal(presented.items[0].explanation, "Tarifa sintética 28.50 EUR/m²");
  assert.deepEqual(presented.assumptions, ["Tarifas sintéticas"]);
});

test("field states map each value to its own information class", () => {
  assert.equal(fieldOrigin("observed"), "observed");
  assert.equal(fieldOrigin("calculated"), "derived");
  assert.equal(fieldOrigin("confirmed"), "human_confirmed");
  assert.equal(fieldOrigin("unknown"), "unknown");
});

test("initial result shows scenario proposals when reviewed pieces are still empty", () => {
  const proposal = { id: "proposal-side", label: "Lateral" };
  const model = componentsForSnapshot({
    result: { pieces: [], scenarios: [{ id: "scenario-a", components: [proposal] }] },
  });
  assert.deepEqual(model.components, [proposal]);
  assert.equal(model.scenarios[0].id, "scenario-a");
});

test("reviewed pieces replace hypotheses after a human decision", () => {
  const piece = { id: "piece-side", label: "Lateral confirmado" };
  const model = componentsForSnapshot({
    result: { pieces: [piece], scenarios: [{ id: "scenario-a", components: [{ id: "proposal-side" }] }] },
  });
  assert.deepEqual(model.components, [piece]);
});

test("terminal review state no longer reads as processing", () => {
  assert.deepEqual(snapshotStatusPresentation({ state: "needs_review", result: { state: "needs_review" } }), { label: "Revisión necesaria", message: "Geometría extraída. Revisa las hipótesis antes de exportar." });
  assert.deepEqual(snapshotStatusPresentation({ state: "needs_review", result: { state: "completed" } }), { label: "Completado", message: "Resultado revisado y listo para estimar o exportar." });
});

test("restored execution mode is labeled independently from the next run selector", () => {
  assert.equal(executionModeLabel("geometry_only"), "Ejecución: solo geometría");
  assert.equal(executionModeLabel("live"), "Ejecución: agente en vivo");
});

test("recorded replay is presented as offline provenance rather than a new inference", () => {
  const replay = presentReplaySource({ mode: "recorded_replay", replay_source: {
    recording_id: `recording-${"a".repeat(64)}`, recording_version: 1,
    source_live_run_id: `run-${"b".repeat(32)}`, source_result_revision: 3, source_actor: "ana",
    provider_model: "gpt-model", provider_response_ids: ["response-1"], transcript_sha256: "c".repeat(64), fingerprint: "d".repeat(64), recorded_at: "2026-11-14T12:00:00Z",
  } });
  assert.equal(replay.available, true);
  assert.match(replay.summary, /Reproducción offline/);
  assert.match(replay.summary, /origen live/);
  assert.match(replay.summary, /ana/);
  assert.match(replay.detail, /gpt-model/);
  assert.equal(presentReplaySource({ mode: "live" }).available, false);
  assert.equal(executionModeLabel("recorded_replay"), "Ejecución: reproducción offline");
});
