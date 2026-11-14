import test from "node:test";
import assert from "node:assert/strict";

import { browserStorage, clearRunSession, createResilientStorage, persistJob, persistRunId, restoredRunRecovery, restoreJob, restoreRunId } from "../core/session.js";

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

test("transient restored run failures preserve the only recovery pointer and allow retry", () => {
  for (const error of [{ status: 0, code: "network_error", retryable: true }, { status: 502, code: "bad_gateway" }, { status: 401, code: "unauthorized" }]) {
    assert.deepEqual(restoredRunRecovery("run-abc123", error), { discard: false, retry: true, reason: "temporarily_unavailable" });
  }
});

test("only an invalid run id or confirmed 404 discards a restored pointer", () => {
  assert.deepEqual(restoredRunRecovery("../not-a-run", { status: 0 }), { discard: true, retry: false, reason: "invalid_run_id" });
  assert.deepEqual(restoredRunRecovery("run-abc123", { status: 404, code: "run_not_found" }), { discard: true, retry: false, reason: "run_not_found" });
  assert.deepEqual(restoredRunRecovery("run-abc123", { status: 404, code: "invalid_response" }), { discard: false, retry: true, reason: "temporarily_unavailable" });
  assert.equal(restoredRunRecovery("run-abc123", { status: 422 }).discard, false);
});

test("blocked browser storage falls back to memory without evaluating the getter again", () => {
  let reads = 0;
  const scope = {};
  Object.defineProperty(scope, "localStorage", { get() { reads += 1; throw new DOMException("blocked", "SecurityError"); } });
  const store = browserStorage(scope);
  persistJob({ id: "job-memory", state: "queued" }, store);
  assert.deepEqual(restoreJob(store), { id: "job-memory", run_id: null, state: "queued" });
  assert.equal(reads, 1);
});

test("quota failures keep the newest run in memory and still update the URL", () => {
  const primary = { getItem: () => "run-stale", setItem() { throw new DOMException("full", "QuotaExceededError"); }, removeItem() { throw new DOMException("blocked", "SecurityError"); } };
  const store = createResilientStorage(primary); let changedUrl;
  persistRunId("run-current", store, { pathname: "/", search: "", hash: "" }, { replaceState: (_state, _title, url) => { changedUrl = url; } });
  assert.equal(restoreRunId({ search: "" }, store), "run-current");
  assert.equal(changedUrl, "/?run=run-current");
});

test("history replacement failures never break persistence or clearing", () => {
  const store = createResilientStorage(null);
  const blockedHistory = { replaceState() { throw new DOMException("opaque origin", "SecurityError"); } };
  assert.doesNotThrow(() => persistRunId("run-memory", store, { pathname: "/", search: "", hash: "" }, blockedHistory));
  assert.equal(restoreRunId({ search: "" }, store), "run-memory");
  assert.doesNotThrow(() => clearRunSession(store, { pathname: "/", search: "?run=run-memory", hash: "" }, blockedHistory));
  assert.equal(restoreRunId({ search: "" }, store), null);
});

test("cancelled jobs do not survive reload as active work", () => {
  const store=storage();persistJob({id:"job-cancelled",state:"running"},store);persistJob({id:"job-cancelled",state:"cancelled"},store);
  assert.equal(restoreJob(store),null);
});

test("exported session helpers tolerate raw throwing storage", () => {
  const blocked={getItem(){throw new DOMException("blocked","SecurityError");},setItem(){throw new DOMException("blocked","SecurityError");},removeItem(){throw new DOMException("blocked","SecurityError");}};
  let changedUrl;
  assert.equal(restoreRunId({search:""},blocked),null);
  assert.doesNotThrow(()=>persistJob({id:"job-raw",state:"queued"},blocked));
  assert.doesNotThrow(()=>persistRunId("run-raw",blocked,{pathname:"/",search:"",hash:""},{replaceState:(_a,_b,url)=>{changedUrl=url;}}));
  assert.equal(changedUrl,"/?run=run-raw");
  assert.doesNotThrow(()=>clearRunSession(blocked,{pathname:"/",search:"?run=run-raw",hash:""},{replaceState(){}}));
});
