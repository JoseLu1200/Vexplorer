import test from "node:test";
import assert from "node:assert/strict";

import { createStore } from "../core/state.js";

test("loading a new run clears selections from the previous run", () => {
  const store = createStore();
  store.dispatch({ type: "RUN_LOADING", runId: "run-1" });
  store.dispatch({ type: "SELECTION_CHANGED", selection: { componentId: "part-1" } });
  store.dispatch({ type: "RUN_LOADING", runId: "run-2" });

  assert.equal(store.getState().runId, "run-2");
  assert.deepEqual(store.getState().selection, {});
  assert.equal(store.getState().phase, "loading");
});

test("a partial result preserves drawing data and enters review phase", () => {
  const store = createStore();
  const drawing = { drawing_id: "drawing-1", source_unit: "unknown" };
  store.dispatch({ type: "RUN_LOADING", runId: "run-1" });
  store.dispatch({ type: "SNAPSHOT_RECEIVED", snapshot: { state: "needs_review", drawing } });

  assert.equal(store.getState().phase, "review");
  assert.equal(store.getState().snapshot.drawing, drawing);
});
