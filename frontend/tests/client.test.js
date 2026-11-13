import test from "node:test";
import assert from "node:assert/strict";

import { ApiError, createApiClient } from "../api/client.js";

function response(status, body, headers = {}) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

test("the API client unwraps the canonical data envelope", async () => {
  const fetchImpl = async () => response(200, { schema_version: "0.2.0", data: { state: "needs_review" }, meta: {} });
  const client = createApiClient({ fetchImpl });

  assert.deepEqual(await client.getRun("run 1"), { state: "needs_review" });
});

test("the API client keeps a specific backend error for the interface", async () => {
  const fetchImpl = async () => response(409, {
    schema_version: "0.2.0",
    error: { code: "stale_result_revision", message: "La revisión ya cambió", details: {}, retryable: false },
    meta: {},
  });
  const client = createApiClient({ fetchImpl });

  await assert.rejects(client.getRun("run-1"), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.code, "stale_result_revision");
    assert.equal(error.status, 409);
    return true;
  });
});

test("review requests send the base revision and an idempotency key", async () => {
  let request;
  const fetchImpl = async (url, init) => {
    request = { url, init };
    return response(201, { schema_version: "0.2.0", data: { result_revision: 2 }, meta: {} });
  };
  const client = createApiClient({ fetchImpl, idFactory: () => "review-key" });
  await client.review("run-1", { base_result_revision: 1, decisions: [] });

  assert.equal(request.url, "/api/v1/runs/run-1/reviews");
  assert.equal(request.init.headers["Idempotency-Key"], "review-key");
  assert.deepEqual(JSON.parse(request.init.body), { base_result_revision: 1, decisions: [] });
});
