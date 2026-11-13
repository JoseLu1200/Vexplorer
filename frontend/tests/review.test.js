import test from "node:test";
import assert from "node:assert/strict";

import { buildReviewPayload, buildScenarioReviewPayload } from "../core/review.js";

test("review payload preserves base revision and excludes client reviewer identity", () => {
  const payload = buildReviewPayload({ result_revision: 3 }, [{ scenario_id: "scenario-a", decision: "accept", reason: "Montaje confirmado en taller" }]);
  assert.deepEqual(payload, {
    base_result_revision: 3,
    decisions: [{ scenario_id: "scenario-a", decision: "accept", reason: "Montaje confirmado en taller" }],
  });
  assert.equal("reviewer_id" in payload, false);
});

test("review decisions require a written reason", () => {
  assert.throws(() => buildReviewPayload({ result_revision: 1 }, [{ scenario_id: "a", decision: "accept", reason: " " }]), /motivo/i);
});

test("scenario review sends technical premises without calculating dimensions in the browser", () => {
  assert.deepEqual(buildScenarioReviewPayload({ result_revision: 2 }, {
    scenario_id: "between-sides",
    confirmed_thickness_mm: "18",
    material: "Melamina blanca",
    finish: "Canto ABS",
    notes: "Montaje confirmado por el responsable de taller",
  }), {
    base_result_revision: 2,
    scenario_id: "between-sides",
    confirmed_thickness_mm: 18,
    material: "Melamina blanca",
    finish: "Canto ABS",
    notes: "Montaje confirmado por el responsable de taller",
  });
});

test("scenario review rejects a missing or non positive thickness", () => {
  assert.throws(() => buildScenarioReviewPayload({ result_revision: 1 }, { scenario_id: "a", confirmed_thickness_mm: "0", notes: "motivo" }), /espesor/i);
});
