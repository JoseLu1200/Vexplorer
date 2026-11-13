import test from "node:test";
import assert from "node:assert/strict";

import { availableModes, componentsForSnapshot, presentEstimate } from "../core/presentation.js";

test("geometry only stays available while unconfigured provider modes stay disabled", () => {
  assert.deepEqual(availableModes({ live_available: false, replay_available: false }), [
    { id: "geometry_only", enabled: true },
    { id: "live", enabled: false },
    { id: "recorded_replay", enabled: false },
  ]);
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
