import test from "node:test";
import assert from "node:assert/strict";

import { buildReviewPayload } from "../core/review.js";

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
