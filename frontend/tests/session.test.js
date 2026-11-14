import test from "node:test";
import assert from "node:assert/strict";

import { clearRunSession, persistJob, persistRunId, restoreJob, restoreRunId } from "../core/session.js";

function storage() {
  const values = new Map();
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
}

test("URL run identifier wins over local persisted state", () => {
  const store = storage(); store.setItem("vexplorer.run_id", "run-old");
  assert.equal(restoreRunId({ search: "?run=run-url" }, store), "run-url");
});

test("persisted run updates storage and URL without navigation", () => {
  const store = storage(); let changedUrl;
  persistRunId("run-2", store, { pathname: "/", search: "", hash: "" }, { replaceState: (_state, _title, url) => { changedUrl = url; } });
  assert.equal(store.getItem("vexplorer.run_id"), "run-2");
  assert.equal(changedUrl, "/?run=run-2");
});

test("clearing a run removes persisted identity and query parameter", () => {
  const store = storage(); store.setItem("vexplorer.run_id", "run-2"); let changedUrl;
  clearRunSession(store, { pathname: "/", search: "?run=run-2", hash: "#review" }, { replaceState: (_state, _title, url) => { changedUrl = url; } });
  assert.equal(store.getItem("vexplorer.run_id"), null);
  assert.equal(changedUrl, "/#review");
});

test("an unfinished job survives reload until a run replaces it", () => {
  const store = storage();
  persistJob({ id: "job-7", run_id: null, state: "running" }, store);
  assert.deepEqual(restoreJob(store), { id: "job-7", run_id: null, state: "running" });
  persistRunId("run-7", store, { pathname: "/", search: "", hash: "" }, { replaceState() {} });
  assert.equal(restoreJob(store), null);
});

test("invalid persisted job data is ignored", () => {
  const store = storage(); store.setItem("vexplorer.job", "not-json");
  assert.equal(restoreJob(store), null);
});
