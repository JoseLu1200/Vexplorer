import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { jobStatusLabel, pollJob } from "../core/jobs.js";

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

test("job polling preserves recovery checkpoint and cause",async()=>{
  const result=await pollJob("job-recover",{getJob:async()=>({id:"job-recover",state:"interrupted",run_id:"run-1",cause:"provider_timeout",checkpoint:{phase:"proposal",proposal_saved:true,proposal_id:"proposal-1",proposal_revision:2,review_revision:0},recovery:{safe_action:"resume_review",endpoint:"/api/v1/jobs/job-recover/resume"}}),wait:async()=>{}});
  assert.equal(result.cause,"provider_timeout");
  assert.deepEqual(result.checkpoint,{phase:"proposal",proposal_saved:true,proposal_id:"proposal-1",proposal_revision:2,review_revision:0});
  assert.equal(result.recovery.safe_action,"resume_review");
});

test("job polling exposes a specific provider reason inside the API wrapper",async()=>{
  const result=await pollJob("job-credit",{
    getJob:async()=>({id:"job-credit",state:"failed",error:{code:"general_live_provider_failed",reason_code:"provider_credit_balance_exhausted"}}),
    wait:async()=>{throw new Error("must not wait after terminal state");},
  });

  assert.equal(result.cause,"provider_credit_balance_exhausted");
  assert.equal(result.error.code,"general_live_provider_failed");
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

test("job polling stops locally after ten minutes without cancelling the durable job", async()=>{
  let now=0,calls=0;
  await assert.rejects(()=>pollJob("job-long",{
    getJob:async()=>{calls+=1;return{id:"job-long",state:"running"};},
    wait:async(milliseconds)=>{now+=milliseconds;},
    now:()=>now,
    intervalMs:100_000,
    timeoutMs:600_000,
  }),(error)=>error.name==="TimeoutError"&&/servidor/.test(error.message));
  assert.equal(calls,6);
});

test("cancelled is terminal and preserves durable cancellation metadata", async () => {
  const result = await pollJob("job-cancelled", {
    getJob: async () => ({ id: "job-cancelled", state: "cancelled", queue_position: null, cancel_requested: true, error: { code: "job_cancelled", message: "Cancelado" } }),
    wait: async () => { throw new Error("must not wait after cancellation"); },
  });
  assert.equal(result.state, "cancelled");
  assert.equal(result.cancelRequested, true);
});

test("queue labels expose position and pending cancellation", () => {
  assert.equal(jobStatusLabel({ state: "queued", queuePosition: 3 }), "En cola · posición 3");
  assert.equal(jobStatusLabel({ state: "running", cancelRequested: true }), "Cancelación solicitada…");
  assert.equal(jobStatusLabel({ state: "cancelled" }), "Análisis cancelado");
});
