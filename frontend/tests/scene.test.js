import test from "node:test";
import assert from "node:assert/strict";
import { normaliseScene, sceneMeshCenter } from "../core/scene.js";

test("scene refuses objects with incomplete dimensions instead of inventing geometry", () => {
  const scene = normaliseScene({ state: "incomplete", warnings: ["Falta grosor"], objects: [
    { piece_id: "p1", label: "Lateral", position_mm: { x: 0, y: 0, z: 0 }, dimensions_mm: { x: 300, y: 1200, z: null } },
  ] });
  assert.equal(scene.objects.length, 0);
  assert.match(scene.warnings.join(" "), /Falta grosor/);
});

test("scene keeps backed occurrences and their evidence identifiers", () => {
  const scene = normaliseScene({ state: "ready", objects: [
    { piece_id: "p1", proposal_id: "c1", occurrence_index: 2, position_mm: { x: 0, y: 1, z: 2 }, dimensions_mm: { x: 300, y: 1200, z: 18 }, evidence_ids: ["ev1"], placement_basis: "review" },
  ] });
  assert.equal(scene.objects[0].key, "p1:2");
  assert.deepEqual(scene.objects[0].dimensions, [300, 1200, 18]);
  assert.deepEqual(scene.objects[0].evidenceIds, ["ev1"]);
  assert.deepEqual(sceneMeshCenter(scene.objects[0]), [150, 601, 11]);
});

test("parts-only scene preserves observation, placement state and assumptions", () => {
  const scene = normaliseScene({ state: "ready", assumptions: ["Reconstrucción derivada"], objects: [{
    piece_id: "piece-1", proposal_id: "candidate-1", part_observation_id: "part-obs-A", occurrence_index: 1,
    position_mm: { x: 0, y: 0, z: 0 }, dimensions_mm: { x: 900, y: 300, z: 18 },
    placement_status: "hypothesis", placement_constraint_ids: ["constraint-1"], placement_basis: "candidate",
  }] });
  assert.equal(scene.objects[0].partObservationId, "part-obs-A");
  assert.equal(scene.objects[0].placementStatus, "hypothesis");
  assert.deepEqual(scene.objects[0].placementConstraintIds, ["constraint-1"]);
  assert.deepEqual(scene.assumptions, ["Reconstrucción derivada"]);
});
