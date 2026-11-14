import test from "node:test";
import assert from "node:assert/strict";
import { cameraZoomPosition, normaliseScene, sceneMeshCenter } from "../core/scene.js";
import { observeContainerSize, resizeRendererToContainer } from "../components/SceneViewer.js";

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

test("3D toolbar zoom keeps the orbit target and moves the camera", () => {
  assert.deepEqual(cameraZoomPosition([100, 50, 100], [20, 10, 20], .5), [60, 30, 60]);
});

test("3D viewer follows container reflow and stops observing after disposal", () => {
  const observed = [];
  const disconnected = [];
  let notify;
  class FakeResizeObserver {
    constructor(callback) { notify = callback; }
    observe(element) { observed.push(element); }
    disconnect() { disconnected.push(true); }
  }
  const root = { id: "scene-root" };
  let resizeCount = 0;

  const stop = observeContainerSize(root, () => { resizeCount += 1; }, FakeResizeObserver);
  assert.deepEqual(observed, [root]);
  assert.equal(resizeCount, 1, "the initial canvas size is synchronized immediately");

  notify();
  assert.equal(resizeCount, 2, "layout-only changes synchronize the renderer without a window resize");

  stop();
  assert.deepEqual(disconnected, [true]);
});

test("3D viewer keeps its last valid projection while hidden and resizes when visible again", () => {
  let rect = { width: 0, height: 0 };
  const sizes = [];
  let projectionUpdates = 0;
  let draws = 0;
  const root = { getBoundingClientRect: () => rect };
  const renderer = { setSize: (...size) => sizes.push(size) };
  const camera = { aspect: 1, updateProjectionMatrix: () => { projectionUpdates += 1; } };

  assert.equal(resizeRendererToContainer(root, renderer, camera, () => { draws += 1; }), false);
  assert.deepEqual(sizes, []);
  assert.equal(camera.aspect, 1);

  rect = { width: 900, height: 450 };
  assert.equal(resizeRendererToContainer(root, renderer, camera, () => { draws += 1; }), true);
  assert.deepEqual(sizes, [[900, 450, false]]);
  assert.equal(camera.aspect, 2);
  assert.equal(projectionUpdates, 1);
  assert.equal(draws, 1);
});
