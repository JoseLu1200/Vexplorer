import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { pollJob } from "../core/jobs.js";

const appSource = readFileSync(new URL("../app.js", import.meta.url), "utf8");

test("the application polls durable jobs and never opens finite history as EventSource", () => {
  assert.match(appSource, /api\.createJob/);
  assert.match(appSource, /pollJob/);
  assert.match(appSource, /restoreJob/);
  assert.doesNotMatch(appSource, /new EventSource/);
});

test("job polling reports ordered states and resolves the durable run", async () => {
  const responses = [
    { id: "job-1", state: "queued", run_id: null },
    { id: "job-1", state: "running", run_id: "run-1" },
    { id: "job-1", state: "succeeded", run_id: "run-1" },
  ];
  const seen = [];
  const result = await pollJob("job-1", {
    getJob: async () => responses.shift(),
    wait: async () => {},
    onUpdate: (job) => seen.push(job.state),
  });
  assert.deepEqual(seen, ["queued", "running", "succeeded"]);
  assert.equal(result.runId, "run-1");
});

test("job polling preserves the server error and stops at failed", async () => {
  const result = await pollJob("job-2", {
    getJob: async () => ({ id: "job-2", state: "failed", run_id: null, error: { code: "worker_interrupted", message: "Trabajo interrumpido" } }),
    wait: async () => { throw new Error("must not wait after terminal state"); },
  });
  assert.equal(result.state, "failed");
  assert.equal(result.error.message, "Trabajo interrumpido");
});

test("job polling aborts without issuing another request", async () => {
  const controller = new AbortController(); let calls = 0;
  await assert.rejects(() => pollJob("job-3", {
    signal: controller.signal,
    getJob: async () => { calls += 1; controller.abort(); return { id: "job-3", state: "running" }; },
    wait: async () => {},
  }), (error) => error.name === "AbortError");
  assert.equal(calls, 1);
});
