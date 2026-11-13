import test from "node:test";
import assert from "node:assert/strict";
import { createRequestFence } from "../core/request-fence.js";

test("a deferred response cannot overwrite a newer run or revision", async () => {
  const fence = createRequestFence();
  let resolveOld;
  const oldResponse = new Promise((resolve) => { resolveOld = resolve; });
  const oldToken = fence.issue("run-a:2");
  const applied = [];
  const oldTask = oldResponse.then((value) => { if (fence.isCurrent(oldToken, "run-a:2")) applied.push(value); });
  const newToken = fence.issue("run-b:1");
  if (fence.isCurrent(newToken, "run-b:1")) applied.push("new");
  resolveOld("old"); await oldTask;
  assert.deepEqual(applied, ["new"]);
});

test("reset invalidates an in-flight request even without a replacement", () => {
  const fence = createRequestFence(); const token = fence.issue("run-a:1"); fence.invalidate();
  assert.equal(fence.isCurrent(token, "run-a:1"), false);
});

test("a late rejected upload cannot publish its obsolete error", async () => {
  const fence=createRequestFence(); let rejectOld;
  const deferred=new Promise((_,reject)=>{rejectOld=reject;}); const token=fence.issue("file-a"); const messages=[];
  const task=deferred.catch((error)=>{if(fence.isCurrent(token,"file-a"))messages.push(error.message);});
  fence.issue("file-b"); rejectOld(new Error("falló A")); await task;
  assert.deepEqual(messages,[]);
});
