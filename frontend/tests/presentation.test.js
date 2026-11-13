import test from "node:test";
import assert from "node:assert/strict";

import { availableModes, presentEstimate } from "../core/presentation.js";

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
